Convert kotatsu backup to Mihon backup
Input format from Kotatsu: zip file with multiple JSON inside
Output format for Mihon: protobuf (schema in kahon_backup.proto)
Edit distance lib from https://github.com/belambert/edit-distance

How to:

Restoring a Mihon backup wipes all previous config and favorites. To avoid this issue an exisitng backup will be used as a template and expanded with the entries imported from kotatsu.

1. Export backup from kotatsu.
2. List all sources used by kotatsu: kot2ka.py -l -k <kotatsu_backup.zip>
3. Install Mihon or any of its forks (Kahon/Kumo...).
4. Install in Mihon all sources used by the Kotatsu backup.
5. Create a temporal category in Mihon 'kotatsu_refs' and add any manga from each source in the kotatsu backup to this category.
6. Create Mihon backup. This can be used to undo any changes so keep a copy of the file somewhere safe.
7. Run this script as './kot2ka.py -k <kotatsu backup> -n <Mihon backup> -o <new Mihon backup to create>'
8. Restore the new Mihon backup. If anything is not to your liking, restore the original Mihon back to undo any changes.
9. Clean up: remove the temporal category "kotatsu_refs" and its mangas. Organize/rename the new categories and their mangas.
    You may need to enable "Reindex downloads" so the metadata for each new manga is fetched.
