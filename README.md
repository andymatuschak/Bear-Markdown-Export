## Markdown export and sync of Bear notes

***bear_export_sync.py***   
*Version 1.4, 2020-01-11*

Python script for export and roundtrip sync of Bear's notes to OneDrive, Dropbox, etc. and edit online with [StackEdit](https://stackedit.io/app), or use a markdown editor like *Typora* on Windows or a suitable app on Android. Remote edits and new notes get synced back into Bear with this script.

**See also: [Bear Markdown and textbundle import – with tags from file and folder](Bear%20Import.md)**

Set up seamless syncing with Ulysses’ external folders on Mac, with images included!  
Write and add photos in Bear, then reorder, glue, and publish, export, or print with styles in Ulysses—  
bears and butterflies are best friends ;)  
(PS. The manual order you set for notes in Ulysses' external folder, is maintained during syncs, unless title is changed.) 

Suitable for use with https://github.com/andymatuschak/note-link-janitor.

BEAR IN MIND! This is a free to use version, and please improve or modify as needed. But do be careful! both `rsync` and `shutil.rmtree` used here, are powerful commands that can wipe clean a whole folder tree or even your complete HD if paths are set incorrectly! Also, be safe, take a fresh backup of both Bear and your Mac before first run.

*See also: [Bear Power Pack](https://github.com/rovest/Bear-Power-Pack/blob/master/README.md)*

## Usage

```
python bear_export_sync.py --out ~/Notes/Bear --backup ~/Notes/Backup
```

See `--help` for more.

## Features

* Bear notes exported as plain Markdown or Textbundles with images.
* Syncs external edits back to Bear with original image links intact. 
* New external `.md` files or `.textbundles` are added.  
(Tags created from sub folder name)
* Export option: Make nested folders from tags.   
For first tag only, or all tags (duplicates notes)
* Export option: Include or exclude export of notes with specific tags.
* Export option: Export as `.textbundles` with images included. 
* Or as: `.md` with links to common image repository 
* Export option: Hide tags in HTML comments like: `<!-- #mytag -->` if `hide_tags_in_comment_block = True`
* **NEW** Hybrid export: `.textbundles` of notes with images, otherwise regular `.md` (Makes it easier to browse and edit on other platforms.)
* **NEW** Writes log to `bear_export_sync_log.txt` in `BearSyncBackup` folder.

Edit your Bear notes online in browser on [OneDrive.com](https://onedrive.live.com). It has a ok editor for plain text/markdown. Or with [StackEdit](https://stackedit.io/app), an amazing online markdown editor that can sync with *Dropbox* or *Google Drive*

Read and edit your Bear notes on *Windows* or *Android* with any markdown editor of choice. Remote edits or new notes will be synced back into Bear again. *Typora* works great on Windows, and displays images of text bundles as well.

NOTE! If syncing with Ulysses’ external folders on Mac, remember to edit that folder settings to `.textbundle` and `Inline Links`!

Run script manually or add it to a cron job for automatic syncing (every 5 – 15 minutes, or whatever you prefer).  
([LaunchD Task Scheduler](https://itunes.apple.com/us/app/launchd-task-scheduler/id620249105?mt=12) Is easy to configure and works very well for this) 


### Syncs external edits back into Bear
Script first checks for external edits in Markdown files or textbundles (previously exported from Bear as described below):

* It replaces text in original note with `bear://x-callback-url/add-text?mode=replace` command   
(That way keeping original note ID and creation date)  
If any changes to title, new title will be added just below original title.  
(`mode=replace` does not replace title)
* Original note in `sqlite` database and external edit are both backed up as markdown-files to BearSyncBackup folder before import to bear.
* If a sync conflict, both original and new version will be in Bear (the new one with a sync conflict message and link to original).
* New notes created online, are just added to Bear  
(with the `bear://x-callback-url/create` command)
* If a textbundle gets new images from an external app, it will be opened and imported as a new note in Bear, with message and link to original note.  
(The `subprocess.call(['open', '-a', '/applications/bear.app', bundle])` command is used for this)


### Markdown export to Dropbox, OneDrive, or other:
Then exports all notes from Bear's database.sqlite as plain markdown files:

* Checks modified timestamp on database.sqlite, so exports only when needed.
* Sets Bear note's modification date on exported markdown files.
* Appends Bear note's creation date to filename to avoid “title-filename-collisions”
* Note IDs are included at bottom of markdown files to match original note on sync back:  
	{BearID:730A5BD2-0245-4EF7-BE16-A5217468DF0E-33519-0000429ADFD9221A}  
(these ID's are striped off again when synced back into Bear)
* Uses rsync for copying (from a temp folder), so only changed notes will be synced to Dropbox (or other sync services)
* rsync also takes care of deleting trashed notes
* "Hides” tags from being displayed as H1 in other markdown apps by adding `period+space` in front of first tag on a line:   
`. #bear #idea #python`   
* Or hide tags in HTML comment blocks like: `<!-- #mytag -->` if `hide_tags_in_comment_block = True`   
(these are striped off again when synced back into Bear)
* Makes subfolders named with first tag in note if `make_tag_folders = True`
* Files can now be copied to multiple tag-folders if `multi_tags = True`
* Export can now be restricted to a list of spesific tags: `limit_export_to_tags = ['bear/github', 'writings']`  
or leave list empty for all notes: `limit_export_to_tags = []`
* Can export and link to images in common image repository
* Or export as textbundles with images included 


You have Bear on Mac but also want your notes on your Android phone, on Linux or Windows machine at your office. Or you want them available online in a browser from any desktop computer. Here is a solution (or call it workaround) for now, until Bear comes with an online, Windows, or Android solution ;)

Happy syncing! ;)
