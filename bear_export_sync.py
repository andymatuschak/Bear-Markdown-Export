# encoding=utf-8
# python3.6
# bear_export_sync.py
# Developed with Visual Studio Code with MS Python Extension.

'''
# Markdown export from Bear sqlite database 
Version 1.4, 2020-01-11
modified by: github/andymatuschak, andy_matuschak@twitter
original author: github/rovest, rorves@twitter

See also: bear_import.py for auto import to bear script.

## Sync external updates:
First checks for changes in external Markdown files (previously exported from Bear)
* Replacing text in original note with callback-url replace command   
  (Keeping original creation date)
  If changes in title it will be added just below original title
* New notes are added to Bear (with x-callback-url command)
* New notes get tags from sub folder names, or `#.inbox` if root
* Backing up original note as file to BearSyncBackup folder  
  (unless a sync conflict, then both notes will be there)

## Export:
Then exporting Markdown from Bear sqlite db.
* check_if_modified() on database.sqlite to see if export is needed
* Uses rsync for copying, so only markdown files of changed sheets will be updated  
  and synced by Dropbox (or other sync services)
* "Hides" tags with `period+space` on beginning of line: `. #tag` not appear as H1 in other apps.   
  (This is removed if sync-back above)
* Or instead hide tags in HTML comment blocks like: `<!-- #mytag -->` if `hide_tags_in_comment_block = True`
* Makes subfolders named with first tag in note if `make_tag_folders = True`
* Files can now be copied to multiple tag-folders if `multi_tags = True`
* Export can now be restricted to a list of spesific tags: `limit_export_to_tags = ['bear/github', 'writings']`  
or leave list empty for all notes: `limit_export_to_tags = []`
* Can export and link to images in common image repository
* Or export as textbundles with images included 
'''

multi_tag_folders = True  # Copies notes to all 'tag-paths' found in note!
                          # Only active if `make_tag_folders = True`
hide_tags_in_comment_block = True  # Hide tags in HTML comments: `<!-- #mytag -->`

# The following two lists are more or less mutually exclusive, so use only one of them.
# (You can use both if you have some nested tags where that makes sense)
# Also, they only work if `make_tag_folders = True`.
only_export_these_tags = []  # Leave this list empty for all notes! See below for sample
# only_export_these_tags = ['bear/github', 'writings'] 

export_as_textbundles = False  # Exports as Textbundles with images included
export_as_hybrids = True  # Exports as .textbundle only if images included, otherwise as .md
                          # Only used if `export_as_textbundles = True`
export_image_repository = True  # Export all notes as md but link images to 
                                 # a common repository exported to: `assets_path` 
                                 # Only used if `export_as_textbundles = False`

import os
HOME = os.getenv('HOME', '')
default_out_folder = os.path.join(HOME, "Work", "BearNotes")
default_backup_folder = os.path.join(HOME, "Work", "BearSyncBackup")

# NOTE! Your user 'HOME' path and '/BearNotes' is added below!
# NOTE! So do not change anything below here!!!

import sqlite3
import datetime
import re
import subprocess
import urllib.parse
import time
import shutil
import fnmatch
import json
import argparse

parser = argparse.ArgumentParser(description="Sync Bear notes")
parser.add_argument("--out", default=default_out_folder, help="Path where Bear notes will be synced")
parser.add_argument("--backup", default=default_backup_folder, help="Path where conflicts will be backed up (must be outside of --out)")
parser.add_argument("--images", default=None, help="Path where images will be stored")
parser.add_argument("--attachments", default=None, help="Path where attachments will be stored")
parser.add_argument("--skipImport", action="store_const", const=True, default=False, help="When present, the script only exports from Bear to Markdown; it skips the import step.")
parser.add_argument("--excludeTag", action="append", default=[], help="Don't export notes with this tag. Can be used multiple times.")
parser.add_argument("--disableTagFolders", action="store_const", const=True, default=False, help="Create tag folders")
parsed_args = vars(parser.parse_args())


set_logging_on = True

# NOTE! if 'BearNotes' is left blank, all other files in my_sync_service will be deleted!! 
export_path = parsed_args.get("out")
no_export_tags = parsed_args.get("excludeTag")  # If a tag in note matches one in this list, it will not be exported.
make_tag_folders = not parsed_args.get("disableTagFolders")  # Exports to folders using first tag only, if `multi_tag_folders = False`
# NOTE! "export_path" is used for sync-back to Bear, so don't change this variable name!
multi_export = [(export_path, True)]  # only one folder output here. 
# Use if you want export to severa places like: Dropbox and OneDrive, etc. See below
# Sample for multi folder export:
# export_path_aux1 = os.path.join(HOME, 'OneDrive', 'BearNotes')
# export_path_aux2 = os.path.join(HOME, 'Box', 'BearNotes')

# NOTE! All files in export path not in Bear will be deleted if delete flag is "True"!
# Set this flag fo False only for folders to keep old deleted versions of notes
# multi_export = [(export_path, True), (export_path_aux1, False), (export_path_aux2, True)]

temp_path = os.path.join(HOME, 'Temp', 'BearExportTemp')  # NOTE! Do not change the "BearExportTemp" folder name!!!
bear_db = os.path.join(HOME, 'Library/Group Containers/9K33E3U3T4.net.shinyfrog.bear/Application Data/database.sqlite')
sync_backup = parsed_args.get("backup") # Backup of original note before sync to Bear.
log_file = os.path.join(sync_backup, 'bear_export_sync_log.txt')

# Paths used in image exports:
bear_image_path = os.path.join(HOME,
    'Library/Group Containers/9K33E3U3T4.net.shinyfrog.bear/Application Data/Local Files/Note Images')
assets_path = parsed_args.get("images") if parsed_args.get("images") else os.path.join(export_path, 'BearImages')

bear_files_path = os.path.join(HOME,
    'Library/Group Containers/9K33E3U3T4.net.shinyfrog.bear/Application Data/Local Files/Note Files')
attachments_path = parsed_args.get("attachements") if parsed_args.get("attachements") else os.path.join(export_path, 'BearAttachments')

sync_ts = '.sync-time.log'
export_ts = '.export-time.log'

sync_ts_file = os.path.join(export_path, sync_ts)
sync_ts_file_temp = os.path.join(temp_path, sync_ts)
export_ts_file_exp = os.path.join(export_path, export_ts)
export_ts_file = os.path.join(temp_path, export_ts)

gettag_sh = os.path.join(HOME, 'temp/gettag.sh')
gettag_txt = os.path.join(HOME, 'temp/gettag.txt')


def main():
    init_gettag_script()
    if not parsed_args.get("skipImport"):
        sync_md_updates()
    if check_db_modified():
        delete_old_temp_files()
        note_count = export_markdown()
        write_time_stamp()
        rsync_files_from_temp()
        if export_image_repository and not export_as_textbundles:
            copy_bear_images()
            copy_bear_files()
        # notify('Export completed')
        write_log(str(note_count) + ' notes exported to: ' + export_path)
        exit(1)
    else:
        print('*** No notes needed exports')
        exit(0)


def write_log(message):
    if set_logging_on == True:
        if not os.path.exists(sync_backup):
            os.makedirs(sync_backup)
        time_stamp = datetime.datetime.now().strftime("%Y-%m-%d at %H:%M:%S")
        message = message.replace(export_path + '/', '')
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(time_stamp + ': ' + message + '\n')


def check_db_modified():
    if not os.path.exists(sync_ts_file):
        return True
    db_ts = get_file_date(bear_db)
    last_export_ts = get_file_date(export_ts_file_exp)
    return db_ts > last_export_ts


def export_markdown():
    with sqlite3.connect(bear_db) as conn:
        conn.row_factory = sqlite3.Row
        query = "SELECT * FROM `ZSFNOTE` WHERE `ZTRASHED` LIKE '0' AND `ZARCHIVED` LIKE '0'"
        c = conn.execute(query)
    note_count = 0
    for row in c:
        title = row['ZTITLE']
        md_text = row['ZTEXT'].rstrip()
        creation_date = row['ZCREATIONDATE']
        modified = row['ZMODIFICATIONDATE']
        uuid = row['ZUNIQUEIDENTIFIER']
        filename = clean_title(title)
        file_list = []
        if make_tag_folders:
            file_list = sub_path_from_tag(temp_path, filename, md_text)
        else:
            file_list.append(os.path.join(temp_path, filename))
        if file_list:
            mod_dt = dt_conv(modified)
            md_text = hide_tags(md_text)
            md_text += '\n\n<!-- {BearID:' + uuid + '} -->\n'
            for filepath in file_list:
                note_count += 1
                # print(filepath)
                if export_as_textbundles:
                    if check_image_hybrid(md_text):
                        make_text_bundle(md_text, filepath, mod_dt)                        
                    else:
                        write_file(filepath + '.md', md_text, mod_dt)
                elif export_image_repository:
                    md_proc_text = process_image_links(md_text, filepath)
                    md_proc_text = process_attachments_links(md_proc_text, filepath)
                    write_file(filepath + '.md', md_proc_text, mod_dt)
                else:
                    write_file(filepath + '.md', md_text, mod_dt)
    return note_count


def check_image_hybrid(md_text):
    if export_as_hybrids:
        if re.search(r'\[image:(.+?)\]', md_text):
            return True
        else:
            return False
    else:
        return True


def make_text_bundle(md_text, filepath, mod_dt):
    '''
    Exports as Textbundles with images included 
    '''
    bundle_path = filepath + '.textbundle'
    assets_path = os.path.join(bundle_path, 'assets')    
    if not os.path.exists(bundle_path):
        os.makedirs(bundle_path)
        os.makedirs(assets_path)
        
    info = '''{
    "transient" : true,
    "type" : "net.daringfireball.markdown",
    "creatorIdentifier" : "net.shinyfrog.bear",
    "version" : 2
    }'''
    matches = re.findall(r'\[image:(.+?)\]', md_text)
    for match in matches:
        image_name = match
        new_name = image_name.replace('/', '_')
        source = os.path.join(bear_image_path, image_name)
        target = os.path.join(assets_path, new_name)
        shutil.copy2(source, target)

    md_text = re.sub(r'\[image:(.+?)/(.+?)\]', r'![](assets/\1_\2)', md_text)
    write_file(bundle_path + '/text.md', md_text, mod_dt)
    write_file(bundle_path + '/info.json', info, mod_dt)
    os.utime(bundle_path, (-1, mod_dt))


def sub_path_from_tag(temp_path, filename, md_text):
    # Get tags in note:
    pattern1 = r'(?<!\S)\#([.\w\/\-]+)[ \n]?(?!([\/ \w]+\w[#]))'
    pattern2 = r'(?<![\S])\#([^ \d][.\w\/ ]+?)\#([ \n]|$)'
    if multi_tag_folders:
        # Files copied to all tag-folders found in note
        tags = []
        for matches in re.findall(pattern1, md_text):
            tag = matches[0]
            tags.append(tag)
        for matches2 in re.findall(pattern2, md_text):
            tag2 = matches2[0]
            tags.append(tag2)
        if len(tags) == 0:
            # No tags found, copy to root level only
            return [os.path.join(temp_path, filename)]
    else:
        # Only folder for first tag
        match1 =  re.search(pattern1, md_text)
        match2 =  re.search(pattern2, md_text)
        if match1 and match2:
            if match1.start(1) < match2.start(1):
                tag = match1.group(1)
            else:
                tag = match2.group(1)
        elif match1:
            tag = match1.group(1)
        elif match2:
            tag = match2.group(1)
        else:
            # No tags found, copy to root level only
            return [os.path.join(temp_path, filename)]
        tags = [tag]
    paths = [os.path.join(temp_path, filename)]
    for tag in tags:
        if tag == '/':
            continue
        if only_export_these_tags:
            export = False
            for export_tag in only_export_these_tags:
                if tag.lower().startswith(export_tag.lower()):
                    export = True
                    break
            if not export:
                continue
        for no_tag in no_export_tags:
            if tag.lower().startswith(no_tag.lower()):
                return []
        if tag.startswith('.'):
            # Avoid hidden path if it starts with a '.'
            sub_path = '_' + tag[1:]     
        else:
            sub_path = tag    
        tag_path = os.path.join(temp_path, sub_path)
        if not os.path.exists(tag_path):
            os.makedirs(tag_path)
        paths.append(os.path.join(tag_path, filename))      
    return paths


def process_image_links(md_text, filepath):
    '''
    Bear image links converted to MD links
    '''
    root = filepath.replace(temp_path, '')
    level = len(root.split('/')) - 2
    parent = '../' * level
    md_text = re.sub(r'\[image:(.+?)\]', r'![](' + parent + r'BearImages/\1)', md_text)
    return md_text


def process_attachments_links(md_text, filepath):
    '''
    Bear attachments links converted to MD links
    '''
    root = filepath.replace(temp_path, '')
    level = len(root.split('/')) - 2
    parent = '../' * level
    md_text = re.sub(r'\[file:([^/]+?)\/(.+?)\]', r'[\2](' + parent + r'BearAttachments/\1/\2)', md_text)
    return md_text

def restore_image_links(md_text):
    '''
    MD image links restored back to Bear links
    '''
    #if not re.search(r'!\[.*?\]\(assets/.+?\)', md_text):
        # No image links in note, return unchanged:
    #    return md_text
    if export_as_textbundles:
        md_text = re.sub(r'!\[(.*?)\]\(assets/(.+?)_(.+?)( ".+?")?\) ?', r'[image:\2/\3]\4 \1', md_text)
    elif export_image_repository :
        # md_text = re.sub(r'\[image:(.+?)\]', r'![](../assets/\1)', md_text)
        md_text = re.sub(r'!\[\]\((\.\./)*BearImages/(.+?)\)', r'[image:\2]', md_text)
    return md_text


def copy_bear_images():
    # Image files copied to a common image repository
    subprocess.call(['rsync', '-r', '-t', '--delete', 
                    bear_image_path + "/", assets_path])

def copy_bear_files():
    # Image files copied to a common image repository
    subprocess.call(['rsync', '-r', '-t', '--delete', 
                    bear_files_path + "/", attachments_path])

def write_time_stamp():
    # write to time-stamp.txt file (used during sync)
    write_file(export_ts_file, "Markdown from Bear written at: " +
               datetime.datetime.now().strftime("%Y-%m-%d at %H:%M:%S"), 0)
    write_file(sync_ts_file_temp, "Markdown from Bear written at: " +
               datetime.datetime.now().strftime("%Y-%m-%d at %H:%M:%S"), 0)


def hide_tags(md_text):
    # Hide tags from being seen as H1, by placing `period+space` at start of line:
    if hide_tags_in_comment_block:
        md_text =  re.sub(r'(\n)[ \t]*(\#[^\s#].*)', r'\1<!-- \2 -->', md_text)
    else:
        md_text =  re.sub(r'(\n)[ \t]*(\#[^\s#]+)', r'\1. \2', md_text)
    return md_text


def restore_tags(md_text):
    # Tags back to normal Bear tags, stripping the `period+space` at start of line:
    # if hide_tags_in_comment_block:
    md_text =  re.sub(r'(\n)<!--[ \t]*(\#[^\s#].*?) -->', r'\1\2', md_text)
    # else:
    md_text =  re.sub(r'(\n)\.[ \t]*(\#[^\s#]+)', r'\1\2', md_text)
    return md_text


def clean_title(title):
    title = title[:256].strip()
    if title == "":
        title = "Untitled"
    title = re.sub(r'[/\\*?$@!^&\|~:\.]', r'-', title)
    title = re.sub(r'-$', r'', title)    
    return title.strip()


def write_file(filename, file_content, modified):
    with open(filename, "w", encoding='utf-8') as f:
        f.write(file_content)
    if modified > 0:
        os.utime(filename, (-1, modified))


def read_file(file_name):
    with open(file_name, "r", encoding='utf-8') as f:
        file_content = f.read()
    return file_content


def get_file_date(filename):
    try:
        t = os.path.getmtime(filename)
        return t
    except:
        return 0


def dt_conv(dtnum):
    # Formula for date offset based on trial and error:
    hour = 3600 # seconds
    year = 365.25 * 24 * hour
    offset = year * 31 + hour * 6
    return dtnum + offset


def date_time_conv(dtnum):
    newnum = dt_conv(dtnum) 
    dtdate = datetime.datetime.fromtimestamp(newnum)
    #print(newnum, dtdate)
    return dtdate.strftime(' - %Y-%m-%d_%H%M')


def time_stamp_ts(ts):
    dtdate = datetime.datetime.fromtimestamp(ts)
    return dtdate.strftime('%Y-%m-%d at %H:%M') 


def date_conv(dtnum):
    dtdate = datetime.datetime.fromtimestamp(dtnum)
    return dtdate.strftime('%Y-%m-%d')


def delete_old_temp_files():
    # Deletes all files in temp folder before new export using "shutil.rmtree()":
    # NOTE! CAUTION! Do not change this function unless you really know shutil.rmtree() well!
    if os.path.exists(temp_path) and "BearExportTemp" in temp_path:
        # *** NOTE! Double checking that temp_path folder actually contains "BearExportTemp"
        # *** Because if temp_path is accidentally empty or root,
        # *** shutil.rmtree() will delete all files on your complete Hard Drive ;(
        shutil.rmtree(temp_path)
        # *** NOTE: USE rmtree() WITH EXTREME CAUTION!
    os.makedirs(temp_path)


def rsync_files_from_temp():
    # Moves markdown files to new folder using rsync:
    # This is a very important step! 
    # By first exporting all Bear notes to an emptied temp folder,
    # rsync will only update destination if modified or size have changed.
    # So only changed notes will be synced by Dropbox or OneDrive destinations.
    # Rsync will also delete notes on destination if deleted in Bear.
    # So doing it this way saves a lot of otherwise very complex programing.
    # Thank you very much, Rsync! ;)
    for (dest_path, delete) in multi_export:
        if not os.path.exists(dest_path):
            os.makedirs(dest_path)
        if delete:
            subprocess.call(['rsync', '-r', '-t', '-E', '--delete',
                             '--exclude', 'BearImages/',
                             '--exclude', '.Ulysses*',
                             '--exclude', '*.Ulysses_Public_Filter',
                             temp_path + "/", dest_path])
        else:
            subprocess.call(['rsync', '-r', '-t', '-E',
                            temp_path + "/", dest_path])


def sync_md_updates():
    updates_found = False
    if not os.path.exists(sync_ts_file) or not os.path.exists(export_ts_file):
        return False
    ts_last_sync = os.path.getmtime(sync_ts_file)
    ts_last_export = os.path.getmtime(export_ts_file)
    # Update synced timestamp file:
    update_sync_time_file(0)
    file_types = ('*.md', '*.txt', '*.markdown')
    for (root, dirnames, filenames) in os.walk(export_path):
        '''
        This step walks down into all sub folders, if any.
        '''
        for pattern in file_types:
            for filename in fnmatch.filter(filenames, pattern):
                md_file = os.path.join(root, filename)
                ts = os.path.getmtime(md_file)
                if ts > ts_last_sync:
                    if not updates_found:  # Yet
                        # Wait 5 sec at first for external files to finish downloading from dropbox.
                        # Otherwise images in textbundles might be missing in import:
                        time.sleep(5)
                    updates_found = True
                    md_text = read_file(md_file)
                    backup_ext_note(md_file)
                    if check_if_image_added(md_text, md_file):
                        textbundle_to_bear(md_text, md_file, ts)
                        write_log('Imported to Bear: ' + md_file)
                    else:
                        update_bear_note(md_text, md_file, ts, ts_last_export)
                        write_log('Bear Note Updated: ' + md_file)
    if updates_found:
        # Give Bear time to process updates:
        time.sleep(3)
        # Check again, just in case new updates synced from remote (OneDrive/Dropbox) 
        # during this process!
        # The logic is not 100% fool proof, but should be close to 99.99%
        sync_md_updates() # Recursive call
    return updates_found


def check_if_image_added(md_text, md_file):
    if not '.textbundle/' in md_file:
        return False
    matches = re.findall(r'!\[.*?\]\(assets/(.+?_).+?\)', md_text)
    for image_match in matches:
        'F89CDA3D-3FCC-4E92-88C1-CC4AF46FA733-10097-00002BBE9F7FF804_IMG_2280.JPG'
        if not re.match(r'[0-9A-F]{8}-([0-9A-F]{4}-){3}[0-9A-F]{12}-[0-9A-F]{3,5}-[0-9A-F]{16}_', image_match):
            return True
    return False        


def textbundle_to_bear(md_text, md_file, mod_dt):
    md_text = restore_tags(md_text)
    bundle = os.path.split(md_file)[0]
    match = re.search(r'\{BearID:(.+?)\}', md_text)
    if match:
        uuid = match.group(1)
        # Remove old BearID: from new note
        md_text = re.sub(r'\<\!-- ?\{BearID\:' + uuid + r'\} ?--\>', '', md_text).rstrip() + '\n'
        md_text = insert_link_top_note(md_text, 'Images added! Link to original note: ', uuid)
    else:
        # New textbundle (with images), add path as tag: 
        md_text = get_tag_from_path(md_text, bundle, export_path)
    write_file(md_file, md_text, mod_dt)
    os.utime(bundle, (-1, mod_dt))
    subprocess.call(['open', '-a', '/applications/bear.app', bundle])
    time.sleep(0.5)


def backup_ext_note(md_file):
    if '.textbundle' in md_file:
        bundle_path = os.path.split(md_file)[0]
        bundle_name = os.path.split(bundle_path)[1]
        target = os.path.join(sync_backup, bundle_name)
        bundle_raw = os.path.splitext(target)[0]
        count = 2
        while os.path.exists(target):
            # Adding sequence number to identical filenames, preventing overwrite:
            target = bundle_raw + " - " + str(count).zfill(2) + ".textbundle"
            count += 1
        shutil.copytree(bundle_path, target)
    else:
        # Overwrite former bacups of incoming changes, only keeps last one:
        shutil.copy2(md_file, sync_backup + '/')


def update_sync_time_file(ts):
    write_file(sync_ts_file,
        "Checked for Markdown updates to sync at: " +
        datetime.datetime.now().strftime("%Y-%m-%d at %H:%M:%S"), ts)


def update_bear_note(md_text, md_file, ts, ts_last_export):
    md_text = restore_tags(md_text)
    md_text = restore_image_links(md_text)
    uuid = ''
    match = re.search(r'\{BearID:(.+?)\}', md_text)
    sync_conflict = False
    if match:
        uuid = match.group(1)
        # Remove old BearID: from new note
        md_text = re.sub(r'\<\!-- ?\{BearID\:' + uuid + r'\} ?--\>', '', md_text).rstrip() + '\n'

        sync_conflict = check_sync_conflict(uuid, ts_last_export)
        if sync_conflict:
            link_original = 'bear://x-callback-url/open-note?id=' + uuid
            message = '::Sync conflict! External update: ' + time_stamp_ts(ts) + '::'
            message += '\n[Click here to see original Bear note](' + link_original + ')'
            x_create = 'bear://x-callback-url/create?show_window=no&open_note=no' 
            bear_x_callback(x_create, md_text, message, '')   
        else:
            # Regular external update
            orig_title = backup_bear_note(uuid)
            # message = '::External update: ' + time_stamp_ts(ts) + '::'   
            x_replace = 'bear://x-callback-url/add-text?show_window=no&open_note=no&mode=replace&id=' + uuid
            bear_x_callback(x_replace, md_text, '', orig_title)
            # # Trash old original note:
            # x_trash = 'bear://x-callback-url/trash?show_window=no&id=' + uuid
            # subprocess.call(["open", x_trash])
            # time.sleep(.2)
    else:
        # New external md Note, since no Bear uuid found in text: 
        # message = '::New external Note - ' + time_stamp_ts(ts) + '::' 
        md_text = get_tag_from_path(md_text, md_file, export_path)
        x_create = 'bear://x-callback-url/create?show_window=no' 
        bear_x_callback(x_create, md_text, '', '')
    return


def get_tag_from_path(md_text, md_file, root_path, inbox_for_root=True, extra_tag=''):
    # extra_tag should be passed as '#tag' or '#space tag#'
    path = md_file.replace(root_path, '')[1:]
    sub_path = os.path.split(path)[0]
    tags = []
    if '.textbundle' in sub_path:
        sub_path = os.path.split(sub_path)[0]
    if sub_path == '': 
        if inbox_for_root:
            tag = '#.inbox'
        else:
            tag = ''
    elif sub_path.startswith('_'):
        tag = '#.' + sub_path[1:].strip()
    else:
        tag = '#' + sub_path.strip()
    if ' ' in tag: 
        tag += "#"               
    if tag != '': 
        tags.append(tag)
    if extra_tag != '':
        tags.append(extra_tag)
    for tag in get_file_tags(md_file):
        tag = '#' + tag.strip()
        if ' ' in tag: tag += "#"                   
        tags.append(tag)
    return md_text.strip() + '\n\n' + ' '.join(tags) + '\n'


def get_file_tags(md_file):
    try:
        subprocess.call([gettag_sh, md_file, gettag_txt])
        text = re.sub(r'\\n\d{1,2}', r'', read_file(gettag_txt))
        tag_list = json.loads(text)
        return tag_list
    except:
        return []


def bear_x_callback(x_command, md_text, message, orig_title):
    if message != '':
        lines = md_text.splitlines()
        lines.insert(1, message)
        md_text = '\n'.join(lines)
    if orig_title != '':
        lines = md_text.splitlines()
        title = re.sub(r'^#+ ', r'', lines[0])
        if title != orig_title:
            md_text = '\n'.join(lines)
        else:
            md_text = '\n'.join(lines[1:])        
    x_command_text = x_command + '&text=' + urllib.parse.quote(md_text)
    subprocess.call(["open", "-g", x_command_text])
    time.sleep(.2)


def check_sync_conflict(uuid, ts_last_export):
    conflict = False
    # Check modified date of original note in Bear sqlite db!
    with sqlite3.connect(bear_db) as conn:
        conn.row_factory = sqlite3.Row
        query = "SELECT * FROM `ZSFNOTE` WHERE `ZTRASHED` LIKE '0' AND `ZUNIQUEIDENTIFIER` LIKE '" + uuid + "'"
        c = conn.execute(query)
    for row in c:
        modified = row['ZMODIFICATIONDATE']
        uuid = row['ZUNIQUEIDENTIFIER']
        mod_dt = dt_conv(modified)
        conflict = mod_dt > ts_last_export
    return conflict


def backup_bear_note(uuid):
    # Get single note from Bear sqlite db!
    with sqlite3.connect(bear_db) as conn:
        conn.row_factory = sqlite3.Row
        query = "SELECT * FROM `ZSFNOTE` WHERE `ZUNIQUEIDENTIFIER` LIKE '" + uuid + "'"
        c = conn.execute(query)
    title = ''
    for row in c:  # Will only get one row if uuid is found!
        title = row['ZTITLE']
        md_text = row['ZTEXT'].rstrip()
        modified = row['ZMODIFICATIONDATE']
        mod_dt = dt_conv(modified)
        created = row['ZCREATIONDATE']
        cre_dt = dt_conv(created)
        md_text = insert_link_top_note(md_text, 'Link to updated note: ', uuid)
        dtdate = datetime.datetime.fromtimestamp(cre_dt)
        filename = clean_title(title) + dtdate.strftime(' - %Y-%m-%d_%H%M')
        if not os.path.exists(sync_backup):
            os.makedirs(sync_backup)
        file_part = os.path.join(sync_backup, filename) 
        # This is a Bear text file, not exactly markdown.
        backup_file = file_part + ".txt"
        count = 2
        while os.path.exists(backup_file):
            # Adding sequence number to identical filenames, preventing overwrite:
            backup_file = file_part + " - " + str(count).zfill(2) + ".txt"
            count += 1
        write_file(backup_file, md_text, mod_dt)
        filename2 = os.path.split(backup_file)[1]
        write_log('Original to sync_backup: ' + filename2)
    return title


def insert_link_top_note(md_text, message, uuid):
    lines = md_text.split('\n')
    title = re.sub(r'^#{1,6} ', r'', lines[0])
    link = '::' + message + '[' + title + '](bear://x-callback-url/open-note?id=' + uuid + ')::'        
    lines.insert(1, link) 
    return '\n'.join(lines)


def init_gettag_script():
    gettag_script = \
    '''#!/bin/bash
    if [[ ! -e $1 ]] ; then
    echo 'file missing or not specified'
    exit 0
    fi
    JSON="$(xattr -p com.apple.metadata:_kMDItemUserTags "$1" | xxd -r -p | plutil -convert json - -o -)"
    echo $JSON > "$2"
    '''
    temp = os.path.join(HOME, 'temp')
    if not os.path.exists(temp):
        os.makedirs(temp)
    write_file(gettag_sh, gettag_script, 0)
    subprocess.call(['chmod', '777', gettag_sh])
    

def notify(message):
    title = "ul_sync_md.py"
    try:
        # Uses "terminal-notifier", download at:
        # https://github.com/julienXX/terminal-notifier/releases/download/2.0.0/terminal-notifier-2.0.0.zip
        # Only works with MacOS 10.11+
        subprocess.call(['/Applications/terminal-notifier.app/Contents/MacOS/terminal-notifier',
                         '-message', message, "-title", title, '-sound', 'default'])
    except:
        write_log('"terminal-notifier.app" is missing!')        
    return


if __name__ == '__main__':
    main()
