import csv
import argparse
import os 
import datetime
import subprocess
import json
import xlsxwriter
import vimeo
from pymongo import MongoClient

CLIENT_ID = ''
CLIENT_SECRET = ''
ACCESS_TOKEN = ''

parser = argparse.ArgumentParser(description='Process Baselight and Xytech files, extract shots, and upload to Vimeo')
parser.add_argument('--baselight', type=str, default='Baselight_export_spring2025.txt', help='Baselight export file')
parser.add_argument('--xytech', type=str, help='Xytech file')
parser.add_argument('--verbose', action='store_true', help='Show verbose output')
parser.add_argument('--db', type=str, default='db', help='MongoDB database name')
parser.add_argument('--no-db', action='store_true', help='Skip database operations')
parser.add_argument('--process', type=str, help='Video file to process')
parser.add_argument('--fps', type=float, default=24.0, help='Frames per second')
parser.add_argument('--get-timecode', type=int, help='Convert frame number to timecode')
parser.add_argument('--output', type=str, help='Export to XLS file')
parser.add_argument('--vimeo-upload', action='store_true', help='Upload shots to Vimeo')
parser.add_argument('--unused-frames', action='store_true', help='Export CSV of unused frames')
args = parser.parse_args()

def frame_to_timecode(frame_num, fps):
    total_seconds = frame_num // fps
    frames = int(frame_num % fps)
    hours = int(total_seconds // 3600)
    total_seconds %= 3600
    minutes = int(total_seconds // 60)
    seconds = int(total_seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frames:02d}"

def frame_to_seconds(frame_num, fps):
    return frame_num / fps

if args.get_timecode is not None:
    print(f"Frame {args.get_timecode} {args.fps} fps = {frame_to_timecode(args.get_timecode, args.fps)}")
    if args.process and os.path.exists(args.process):
        frame_file = os.path.join("timecode_extract", f"frame_{args.get_timecode}.jpg")
        subprocess.run(["ffmpeg", "-y", "-ss", str(frame_to_seconds(args.get_timecode, args.fps)), 
                        "-i", args.process, "-vframes", "1", "-q:v", "2", frame_file], 
                        capture_output=True)
    exit(0)

db_client, db_name = None, args.db
use_db = not args.no_db
if use_db:
    db_client = MongoClient('mongodb://localhost:27017/', serverSelectionTimeoutMS=5000)

if args.process:
    video_file = args.process
    if not os.path.exists(video_file):
        print(f"Video file '{video_file}' not found")
        exit(1)
    
    base_name = os.path.splitext(os.path.basename(video_file))[0]
    output_dir = f"{base_name}_processed"
    thumbnails_dir = os.path.join(output_dir, "thumbnails")
    shots_dir = os.path.join(output_dir, "shots")
    
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        
        result = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", 
                            "-show_format", "-show_streams", video_file], 
                            capture_output=True, text=True)
        
        if not result.stdout:
            print(f"Error with {video_file}")
            exit(1)
            
        video_info = json.loads(result.stdout)
        duration_seconds = float(video_info['format'].get('duration', 0))
        fps = args.fps
        
        for stream in video_info.get('streams', []):
            if stream.get('codec_type') == 'video' and 'r_frame_rate' in stream:
                rate_parts = stream['r_frame_rate'].split('/')
                if len(rate_parts) == 2 and int(rate_parts[1]) > 0:
                    fps = float(int(rate_parts[0])) / float(int(rate_parts[1]))
                    break
        
        total_frames = int(duration_seconds * fps)
        print(f"Video: {os.path.basename(video_file)}, Duration: {duration_seconds:.2f}s, FPS: {fps}, Frames: {total_frames}")
        
        if use_db and db_client:
            video_info = {
                'filename': os.path.basename(video_file),
                'path': os.path.abspath(video_file),
                'duration_seconds': duration_seconds,
                'fps': fps,
                'total_frames': total_frames,
                'processed_date': datetime.datetime.now()
            }
            db_client[db_name].video_files.insert_one(video_info)
        
        matching_ranges = []
        not_matching_ranges = []
        single_frames = []
        
        if use_db and db_client:
            for range_doc in db_client[db_name].frame_ranges.find():
                range_str = range_doc['range']
                path = range_doc['path']
                
                if '-' in range_str:
                    start_frame, end_frame = map(int, range_str.split('-'))
                    
                    if end_frame <= total_frames and start_frame != end_frame:
                        mid_frame = start_frame + (end_frame - start_frame) // 2
                        start_tc = frame_to_timecode(start_frame, fps)
                        end_tc = frame_to_timecode(end_frame, fps)
                        mid_tc = frame_to_timecode(mid_frame, fps)
                        
                        thumbnail_path = os.path.join(thumbnails_dir, f"range_{start_frame}_{end_frame}.jpg")
                        try:
                            subprocess.run(["ffmpeg", "-y", "-ss", str(frame_to_seconds(mid_frame, fps)), 
                                        "-i", video_file, "-vframes", "1", "-s", "96x74", "-q:v", "2", thumbnail_path], 
                                        capture_output=True, check=True)
                            thumbnail_success = True
                        except subprocess.CalledProcessError:
                            thumbnail_success = False
                        
                        shot_path = os.path.join(shots_dir, f"shot_{start_frame}_{end_frame}.mp4")
                        try:
                            subprocess.run(["ffmpeg", "-y", "-ss", str(frame_to_seconds(start_frame, fps)), 
                                        "-i", video_file, "-t", str(frame_to_seconds(end_frame - start_frame + 1, fps)),
                                        "-c:v", "libx264", "-preset", "medium", "-crf", "22",
                                        "-c:a", "aac", "-b:a", "128k", shot_path], 
                                        capture_output=True, check=True)
                            shot_success = True
                        except subprocess.CalledProcessError:
                            shot_success = False
                        
                        matching_ranges.append({
                            'path': path,
                            'range': range_str,
                            'start_frame': start_frame,
                            'end_frame': end_frame,
                            'mid_frame': mid_frame,
                            'start_tc': start_tc,
                            'end_tc': end_tc,
                            'mid_tc': mid_tc,
                            'thumbnail_path': thumbnail_path if thumbnail_success else None,
                            'shot_path': shot_path if shot_success else None
                        })
                    else:
                        not_matching_ranges.append({
                            'path': path,
                            'range': range_str,
                            'reason': "Exceeds video duration" if end_frame > total_frames else "Invalid range"
                        })
                else:
                    single_frames.append({
                        'path': path,
                        'frame': range_str,
                        'reason': "Single frame (not a range)"
                    })
            
            if args.unused_frames:
                all_frames = []
                for record in db_client[db_name].baselight.find():
                    path = record.get('mapped_path', '')
                    for frame in record.get('frames', []):
                        all_frames.append((frame, path))
                all_frames.sort()
                
                used_frames = set()
                for r in matching_ranges:
                    path = r['path']
                    start_frame = r['start_frame']
                    end_frame = r['end_frame']
                    for frame in range(start_frame, end_frame + 1):
                        used_frames.add((frame, path))
                
                unused_frames = [f for f in all_frames if f not in used_frames]
                unused_frames_csv = os.path.join(output_dir, "unused_frames.csv")
                with open(unused_frames_csv, 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(['Frame', 'Path', 'Timecode'])
                    for frame, path in unused_frames:
                        timecode = frame_to_timecode(frame, fps)
                        writer.writerow([frame, path, timecode])
                
                print(f"Exported {len(unused_frames)} unused frames {unused_frames_csv}")
                
                if args.output:
                    unused_xls = f"{base_name}_unused_frames.xlsx"
                    try:
                        workbook = xlsxwriter.Workbook(unused_xls)
                        ws = workbook.add_worksheet('Unused Frames')                      
                        ws.write(0, 0, 'Frame')
                        ws.write(0, 1, 'Path')
                        ws.write(0, 2, 'Timecode')
                        
                        for i, (frame, path) in enumerate(unused_frames, 1):
                            ws.write(i, 0, frame)
                            ws.write(i, 1, path)
                            ws.write(i, 2, frame_to_timecode(frame, fps))
                        
                        ws.set_column(0, 0, 10)
                        ws.set_column(1, 1, 40)
                        ws.set_column(2, 2, 15)
                        
                        workbook.close()
                        print(f"Exported unused frames to {unused_xls}")
                    except Exception:
                        print(f"Error creating Excel file")
            
            not_uploaded_csv = os.path.join(output_dir, "not_uploaded.csv")
            with open(not_uploaded_csv, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['Type', 'Path', 'Frame/Range', 'Reason'])
                for r in not_matching_ranges:
                    writer.writerow(['Range', r['path'], r['range'], r['reason']])
                for f in single_frames:
                    writer.writerow(['Single Frame', f['path'], f['frame'], f['reason']])
            
            print(f"Exported {len(not_matching_ranges)} and {len(single_frames)}")
            
            if args.vimeo_upload and all([ACCESS_TOKEN, CLIENT_ID, CLIENT_SECRET]):
                vimeo_links = []
                for i, r in enumerate(matching_ranges):
                    if r['shot_path'] and os.path.exists(r['shot_path']):
                        title = f"Shot {i+1}: {os.path.basename(r['path'])} - {r['range']}"
                        description = f"Path: {r['path']}\nRange: {r['range']}\nTC: {r['start_tc']} to {r['end_tc']}"
                        
                        try:
                            v = vimeo.VimeoClient(token=ACCESS_TOKEN, key=CLIENT_ID, secret=CLIENT_SECRET)
                            uri = v.upload(r['shot_path'])
                            v.patch(uri, data={'name': title, 'description': description})
                            url = f"https://vimeo.com{uri}"
                            
                            vimeo_links.append({'range': r['range'], 'path': r['path'], 'uri': uri, 'url': url})
                            r['vimeo_uri'], r['vimeo_url'] = uri, url
                            print(f"  Uploaded: {url}")
                        except Exception:
                            print(f"Error uploading")
                
                if vimeo_links:
                    with open(os.path.join(output_dir, "vimeo_links.csv"), 'w', newline='') as f:
                        writer = csv.writer(f)
                        writer.writerow(['Path', 'Range', 'Vimeo URI', 'Vimeo URL'])
                        for link in vimeo_links:
                            writer.writerow([link['path'], link['range'], link['uri'], link['url']])
            
            output_file_csv = f"{base_name}_matching_ranges.csv"
            with open(output_file_csv, 'w', newline='') as f:
                writer = csv.writer(f)
                headers = ['Path', 'Frames', 'Start Timecode', 'End Timecode', 'Mid Timecode']
                if args.vimeo_upload:
                    headers.append('Vimeo URL')
                writer.writerow(headers)
                
                for r in matching_ranges:
                    row = [r['path'], r['range'], r['start_tc'], r['end_tc'], r['mid_tc']]
                    if args.vimeo_upload and 'vimeo_url' in r:
                        row.append(r['vimeo_url'])
                    writer.writerow(row)
            
            if args.output:
                xls_file = f"{base_name}_ranges.xlsx"
                
                try:
                    workbook = xlsxwriter.Workbook(xls_file)
            
                    ws = workbook.add_worksheet('Frame Ranges')
                    headers = ['Path', 'Frame Range', 'Start Timecode', 'End Timecode', 'Mid Timecode', 'Thumbnail']
                    if args.vimeo_upload:
                        headers.append('Vimeo URL')
                    
                    for col, header in enumerate(headers):
                        ws.write(0, col, header)
                    
                    for row_idx, r in enumerate(matching_ranges, 1):
                        col = 0
                        ws.write(row_idx, col, r['path']); col += 1
                        ws.write(row_idx, col, r['range']); col += 1
                        ws.write(row_idx, col, r['start_tc']); col += 1
                        ws.write(row_idx, col, r['end_tc']); col += 1
                        ws.write(row_idx, col, r['mid_tc']); col += 1
                        
                        if r['thumbnail_path'] and os.path.exists(r['thumbnail_path']):
                            try:
                                ws.insert_image(row_idx, col, r['thumbnail_path'], {'x_scale': 1, 'y_scale': 1})
                            except Exception:
                                pass
                        col += 1
                        
                        if 'Vimeo URL' in headers and 'vimeo_url' in r:
                            ws.write_url(row_idx, col, r['vimeo_url'], string=r['vimeo_url'])
                    
                    ws.set_column(0, 0, 15)  
                    ws.set_column(1, 1, 15) 
                    ws.set_column(2, 4, 15) 
                    ws.set_column(5, 5, 15)  
                    if args.vimeo_upload:
                        ws.set_column(6, 6, 30) 
                    
                    for row in range(1, len(matching_ranges) + 1):
                        ws.set_row(row, 80)
                    
                    workbook.close()
                    print(f"Data exported {xls_file}")
                except Exception:
                    print(f"Error creating Excel files")
    
    except Exception:
        print(f"Error processing video")
        exit(1)
    
    if not (args.baselight or args.xytech):
        exit(0)

if args.baselight and not os.path.exists(args.baselight):
    print(f"Baselight file '{args.baselight}' isnot found")
    exit(1)

if args.xytech and not os.path.exists(args.xytech):
    print(f"Xytech file '{args.xytech}' is not found")
    exit(1)

if args.baselight:
    frame_list = []
    
    with open(args.baselight, 'r') as f:
        frame_data = f.read()
    
    xytech_locations = []
    path_update = {}
    
    if args.xytech:
        with open(args.xytech, 'r') as xytech_file:
            for line in xytech_file.read().splitlines():
                if line.strip():
                    parts = line.strip().split(',')
                    if len(parts) >= 2:
                        rel_path, full_path = parts[0].strip(), parts[1].strip()
                        xytech_locations.append(rel_path)
                        path_update[rel_path] = full_path
                        
                        if use_db and db_client:
                            xytech_record = {
                                'relative_path': rel_path,
                                'full_path': full_path,
                                'workorder': parts[2].strip() if len(parts) > 2 else 'Unknown',
                                'date_added': datetime.datetime.now()
                            }
                            db_client[db_name].xytech.insert_one(xytech_record)
    else:
        xytech_locations = [
            'reel1/partA/1920x1080', 'reel1/VFX/Hydraulx', 'reel1/VFX/Framestore', 'reel1/VFX/AnimalLogic',
            'reel1/partB/1920x1080', 'pickups/shot_1ab/1920x1080', 'pickups/shot_2b/1920x1080', 'reel1/partC/1920x1080'
        ]
        
        path_update = {
            'reel1/partA/1920x1080': '/hpsans13/production/dogman/reel1/partA/1920x1080',
            'reel1/VFX/Hydraulx': '/hpsans12/production/dogman/reel1/VFX/Hydraulx',
            'reel1/VFX/Framestore': '/hpsans13/production/dogman/reel1/VFX/Framestore',
            'reel1/VFX/AnimalLogic': '/hpsans14/production/dogman/reel1/VFX/AnimalLogic',
            'reel1/partB/1920x1080': '/hpsans13/production/dogman/reel1/partB/1920x1080',
            'pickups/shot_1ab/1920x1080': '/hpsans15/production/dogman/pickups/shot_1ab/1920x1080',
            'pickups/shot_2b/1920x1080': '/hpsans11/production/dogman/pickups/shot_2b/1920x1080',
            'reel1/partC/1920x1080': '/hpsans17/production/dogman/reel1/partC/1920x1080'
        }
        
        if use_db and db_client:
            for rel_path, full_path in path_update.items():
                db_client[db_name].xytech.insert_one({
                    'relative_path': rel_path,
                    'full_path': full_path,
                    'workorder': 'Default',
                    'date_added': datetime.datetime.now()
                })
    
    for line in frame_data.split('\n'):
        parts = line.split()
        if not parts:
            continue
            
        base_path = parts[0]
        path_components = base_path.split('/')

        match_path = ""
        if 'dogman' in path_components:
            dogman_index = path_components.index('dogman')
            match_path = '/' + '/'.join(path_components[dogman_index:])

        full_path, matched_location = base_path, None
        for location in xytech_locations:
            if location in match_path:
                full_path = path_update[location]
                matched_location = location
                break

        frames = []
        for frame in parts[1:]:
            try:
                frame_num = int(frame)
                frames.append(frame_num)
                frame_list.append((frame_num, full_path))
            except ValueError:
                if args.verbose:
                    print(f"Skip frame: {frame}")
        
        if use_db and db_client and frames:
            db_client[db_name].baselight.insert_one({
                'original_path': base_path,
                'mapped_path': full_path,
                'matched_location': matched_location,
                'frames': frames,
                'date_added': datetime.datetime.now()
            })

    frame_list.sort()
    
    ranges = []
    current = {'start': None, 'end': None, 'path': None}
    
    with open('output.csv', 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Path', 'Frames'])
        
        for frame, path in frame_list:
            if current['start'] is None or path != current['path']:
                if current['start'] is not None:
                    range_str = f"{current['start']}-{current['end']}" if current['start'] != current['end'] else str(current['start'])
                    writer.writerow([current['path'], range_str])
                    ranges.append({'path': current['path'], 'range': range_str})
                
                current = {'start': frame, 'end': frame, 'path': path}
            
            elif frame == current['end'] + 1:
                current['end'] = frame
            
            else:
                range_str = f"{current['start']}-{current['end']}" if current['start'] != current['end'] else str(current['start'])
                writer.writerow([current['path'], range_str])
                ranges.append({'path': current['path'], 'range': range_str})
                
                current = {'start': frame, 'end': frame, 'path': path}
        
        if current['start'] is not None:
            range_str = f"{current['start']}-{current['end']}" if current['start'] != current['end'] else str(current['start'])
            writer.writerow([current['path'], range_str])
            ranges.append({'path': current['path'], 'range': range_str})
    
    if use_db and db_client and ranges:
        range_records = []
        for r in ranges:
            range_records.append({
                'path': r['path'],
                'range': r['range'],
                'date_added': datetime.datetime.now()
            })
        db_client[db_name].frame_ranges.insert_many(range_records)
    
    print(f"Processed {len(frame_list)} frames and {len(ranges)} frame ranges")
