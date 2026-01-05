#!/bin/env python3
# Convert kotatsu backup to Kahon backup
# Input format from Kotatsu: zip file with multiple JSON inside
# Output format for Mihon: protobuf (schema in kahon_backup.proto)
# Edit distance lib from https://github.com/belambert/edit-distance

# V 0.1: load categories and manga basic data (manga name/URL/category) and export to Kahon format.
#        No: read progress, per manga/source prefs.

# How to:
# !! Restoring a Mihon backup wipes all previous config and favorites. To avoid this issue an exisitng backup will be
# !! used as a template and expanded with the entries imported from kotatsu.
# 1. Export backup from kotatsu.
# 2. List all sources used by kotatsu: kot2ka.py -l -k <kotatsu_backup.zip>
# 3. Install Mihon or any of its forks (Kahon/Kumo...).
# 4. Install in Mihon all sources used by the Kotatsu backup.
# 5. Create a temporal category in Mihon 'kotatsu_refs' and add any manga from each source in the kotatsu backup to this category.
# 6. Create Mihon backup. This can be used to undo any changes so keep a copy of the file somewhere safe.
# 7. Run this script as './kot2ka.py -k <kotatsu backup> -n <Mihon backup> -o <new Mihon backup to create>'
# 8. Restore the new Mihon backup. If anything is not to your liking, restore the original Mihon back to undo any changes.
# 9. Clean up: remove the tempral category "kotatsu_refs" and its mangas. Organize/rename the new categories and their mangas.

import argparse
from collections import Counter
import gzip
import json
import pprint
import re
import sys
from urllib.parse import urlparse
import zipfile

from google.protobuf import descriptor_pb2
from google.protobuf import descriptor_pool
from google.protobuf import message_factory

import edit_distance

def normalize_source_name(source_name):
    """Normalize source name, help match Kotatsu source name to Mihon source name"""
    source_name = re.sub(r" V\d+$", "", source_name)
    source_name = source_name.replace(" (Unoriginal)", "")
    source_name = source_name.replace("_FUN", "")
    return source_name.lower()

def main(argv):
# arg parsing
    parser = argparse.ArgumentParser(description='Import tracked mangas from a Kotatsu backup into a Mihon backup.')
    parser.add_argument('-l', '--list', action='store_true', help="List short info about the Kotatsu backup")
    parser.add_argument('-k', '--kotatsu_backup', help="Kotatsu backup file to read", required=True, metavar='<IN_FILE>')
    parser.add_argument('-m', '--Mihon_backup', help="Mihon backup file to read", metavar='<IN_FILE>')
    parser.add_argument('-o', '--Mihon_output', help="Mihon backup file to write", metavar='<OUT_FILE>')
    conf = parser.parse_args(argv[1:])
    pprint.pprint(conf)
    if (conf.list and (conf.Mihon_backup is not None or conf.Mihon_output is not None )):
         parser.error(message="Listing Kotatsu metadata must now be mixed with Mihon backups.")
    if (not conf.list and (conf.Mihon_backup is None or conf.Mihon_output is None )):
         parser.error(message="Both Mihon backup files must be configured.")
    proto_file = "kahon_backup.pb2" # ag generateSchemaText, protoc text to pb
# read and parse Kotatsu backup
    # Categories id:title map
    archive = zipfile.ZipFile(conf.kotatsu_backup, 'r')
    categories_json = json.loads(archive.read('categories'))
    #pprint.pprint(categories_json)
    categories = {x['category_id']:x['title'] for x in categories_json}
    pprint.pprint(categories)
    # Mangas
    mangas_json = json.loads(archive.read('favourites'))
    #pprint.pprint(mangas_json)
    mangas = []
    for manga in mangas_json:
        mangas.append((manga['category_id'], manga['manga']['source'], manga['manga']['title'], manga['manga']['public_url']))
    src_use = dict(Counter([x[1] for x in mangas]))
    pprint.pprint(mangas)
# Kotatsu listing logic
    if conf.list:
        # print: categories, sources, mangas
        print("Categories:")
        print("  Id Refs Name")
        print("---- ---- ----")
        cat_use = dict(Counter([x[0] for x in mangas]))
        for k,v in categories.items():
            print("%4s %4d '%s'" % (k, cat_use[k], v))
        print("")
        print("Sources:")
        print("Refs Name")
        print("---- ----")
        for k in sorted(src_use):
            print("%4s '%s'" % (src_use[k], k))
        print("")
        print("Mangas:")
        print("Category    Source             Name          URL")
        print("-------- ------------ ---------------------- ---")
        for manga in mangas:
            print("%8s %-12s %-20s %s" % (manga[0], manga[1], "'"+manga[2]+"'", manga[3]))
        sys.exit(0)
# Read Mihon backup
    protob_f = open(proto_file, 'rb')
    factory_pb = descriptor_pb2.FileDescriptorSet.FromString(protob_f.read())
    pool = descriptor_pool.DescriptorPool()
    pool.Add(factory_pb.file[0])
    backup_desc = pool.FindMessageTypeByName("Backup")
    backup_class = message_factory.GetMessageClass(backup_desc)
    category_desc = pool.FindMessageTypeByName("BackupCategory")
    category_class = message_factory.GetMessageClass(category_desc)
    manga_desc = pool.FindMessageTypeByName("BackupManga")
    manga_class = message_factory.GetMessageClass(manga_desc)

    gunzipped_f=gzip.open(conf.Mihon_backup,'rb')
    gunzipped_data = gunzipped_f.read()
    backup_msg = backup_class.FromString(gunzipped_data)
    #pprint.pprint(backup_msg)
# go
    # read categories, and create new ones for kotatsu
    print(backup_msg.backupCategories)
    max_cat = max([x.id for x in backup_msg.backupCategories])
    max_ord = max([x.order for x in backup_msg.backupCategories])
    print((max_cat, max_ord))
    kot2mih_cat = {}
    for cat_id, cat_name in categories.items():
        max_cat = max_cat + 1
        max_ord = max_ord + 1
        new_cat = category_class()
        new_cat.name = "kotatsu_" + cat_name
        new_cat.id = max_cat
        new_cat.order = max_ord
        new_cat.flags = 64
        kot2mih_cat[cat_id] = new_cat.order
        backup_msg.backupCategories.append(new_cat)
    # Do source matching now
    m_sources = {s.name: s.sourceId for s in backup_msg.backupSources}
    pprint.pprint(src_use)
    pprint.pprint(m_sources)
    sources_map = {}
    match_threshold = 4
    for k_cat in src_use:
        best_match = ""
        best_dist = 1000000
        for m_cat in m_sources:
            distance,_ = edit_distance.edit_distance(normalize_source_name(k_cat), normalize_source_name(m_cat))
            if (distance < best_dist):
                best_match = m_cat
                best_dist = distance
        if (best_dist < match_threshold):
            sources_map[k_cat] = best_match
        else:
            print("Source not matched: '%s', best '%s' distance %d" % (k_cat, best_match, best_dist))
    pprint.pprint(sources_map)
    # for each manga from kotatsu: match source and add entry
    for idx, manga in enumerate(mangas):
        if manga[1] in sources_map:
            new_manga = manga_class()
            new_manga.source = m_sources[sources_map[manga[1]]]
            new_manga.url = urlparse(manga[3]).path
            new_manga.title = manga[2]
            new_manga.categories.append(kot2mih_cat[manga[0]])
            new_manga.initialized = 0
            backup_msg.backupManga.append(new_manga)
            print("(%3d/%3d) Importing manga '%s' from source '%s'" % (idx+1, len(mangas), manga[2], manga[1]))
        else:
            print("(%3d/%3d) SKIP manga '%s': source '%s' not matched" % (idx+1, len(mangas), manga[2], manga[1]))
    # write result
    gzipped_f=gzip.open(conf.Mihon_output,'wb')
    gzipped_f.write(backup_msg.SerializeToString())
    gzipped_f.close()


if __name__ == "__main__":
    main(sys.argv)

#Archive:  kotatsu_20260103-1359.bk.zip
#  Length      Date    Time    Name
#---------  ---------- -----   ----
#       81  01-03-2026 13:59   index
#   665685  01-03-2026 13:59   history
#      260  01-03-2026 13:59   categories
#   167253  01-03-2026 13:59   favourites
#     4480  01-03-2026 13:59   settings
#      269  01-03-2026 13:59   reader_grid
#        2  01-03-2026 13:59   bookmarks
#     8707  01-03-2026 13:59   sources
#        2  01-03-2026 13:59   scrobbling
#        2  01-03-2026 13:59   statistics
#        2  01-03-2026 13:59   saved_filters
#---------                     -------
#   846743                     11 files
# unzip -p kotatsu_20260103-1359.bk.zip categories | jq
# unzip -p kotatsu_20260103-1359.bk.zip favourites | jq

# protoc --descriptor_set_out=kahon_backup.pb2 kahon_backup.proto
# gunzip -c com.amanoteam.kahon_2026-01-03_14-13.tachibk | protoc --decode=Backup kahon_backup.proto > backup_decoded
# gunzip -c out.tachibk | protoc --decode=Backup kahon_backup.proto

# ./kot2ka.py -k kotatsu_20260103-1359.bk.zip -m com.amanoteam.kahon_2026-01-03_14-13.tachibk -o out.tachibk
