# -*- coding: utf-8 -*-

###############################################################################
import logging
import cProfile
import json
import pstats
import sqlite3
from datetime import datetime, timedelta
import StringIO
import time
import unicodedata
import xml.etree.ElementTree as etree
from functools import wraps
from calendar import timegm
import os


import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

###############################################################################

log = logging.getLogger("PLEX."+__name__)

addonName = 'PlexKodiConnect'
WINDOW = xbmcgui.Window(10000)
ADDON = xbmcaddon.Addon(id='plugin.video.plexkodiconnect')

KODILANGUAGE = xbmc.getLanguage(xbmc.ISO_639_1)
KODIVERSION = int(xbmc.getInfoLabel("System.BuildVersion")[:2])

###############################################################################
# Main methods


def window(property, value=None, clear=False, windowid=10000):
    """
    Get or set window property - thread safe!

    Returns unicode.

    Property and value may be string or unicode
    """
    if windowid != 10000:
        win = xbmcgui.Window(windowid)
    else:
        win = WINDOW

    if clear:
        win.clearProperty(property)
    elif value is not None:
        win.setProperty(tryEncode(property), tryEncode(value))
    else:
        return tryDecode(win.getProperty(property))


def settings(setting, value=None):
    """
    Get or add addon setting. Returns unicode

    setting and value can either be unicode or string
    """
    # We need to instantiate every single time to read changed variables!
    addon = xbmcaddon.Addon(id='plugin.video.plexkodiconnect')
    if value is not None:
        # Takes string or unicode by default!
        addon.setSetting(tryEncode(setting), tryEncode(value))
    else:
        # Should return unicode by default, but just in case
        return tryDecode(addon.getSetting(setting))


def language(stringid):
    # Central string retrieval
    return ADDON.getLocalizedString(stringid)


def dialog(type_, *args, **kwargs):

    d = xbmcgui.Dialog()

    if "icon" in kwargs:
        kwargs['icon'] = kwargs['icon'].replace(
            "{plex}",
            "special://home/addons/plugin.video.plexkodiconnect/icon.png")
    if "heading" in kwargs:
        kwargs['heading'] = kwargs['heading'].replace("{plex}",
                                                      language(29999))

    types = {
        'yesno': d.yesno,
        'ok': d.ok,
        'notification': d.notification,
        'input': d.input,
        'select': d.select,
        'numeric': d.numeric
    }
    return types[type_](*args, **kwargs)


def tryEncode(uniString, encoding='utf-8'):
    """
    Will try to encode uniString (in unicode) to encoding. This possibly
    fails with e.g. Android TV's Python, which does not accept arguments for
    string.encode()
    """
    if isinstance(uniString, str):
        # already encoded
        return uniString
    try:
        uniString = uniString.encode(encoding, "ignore")
    except TypeError:
        uniString = uniString.encode()
    return uniString


def tryDecode(string, encoding='utf-8'):
    """
    Will try to decode string (encoded) using encoding. This possibly
    fails with e.g. Android TV's Python, which does not accept arguments for
    string.encode()
    """
    if isinstance(string, unicode):
        # already decoded
        return string
    try:
        string = string.decode(encoding, "ignore")
    except TypeError:
        string = string.decode()
    return string


def DateToKodi(stamp):
        """
        converts a Unix time stamp (seconds passed sinceJanuary 1 1970) to a
        propper, human-readable time stamp used by Kodi

        Output: Y-m-d h:m:s = 2009-04-05 23:16:04

        None if an error was encountered
        """
        try:
            stamp = float(stamp) + float(window('kodiplextimeoffset'))
            date_time = time.localtime(stamp)
            localdate = time.strftime('%Y-%m-%d %H:%M:%S', date_time)
        except:
            localdate = None
        return localdate


def IfExists(path):
    """
    Kodi's xbmcvfs.exists is broken - it caches the results for directories.

    path: path to a directory (with a slash at the end)

    Returns True if path exists, else false
    """
    dummyfile = tryEncode(os.path.join(path, 'dummyfile.txt'))
    try:
        etree.ElementTree(etree.Element('test')).write(dummyfile)
    except:
        # folder does not exist yet
        answer = False
    else:
        # Folder exists. Delete file again.
        xbmcvfs.delete(dummyfile)
        answer = True
    return answer


def IntFromStr(string):
    """
    Returns an int from string or the int 0 if something happened
    """
    try:
        result = int(string)
    except:
        result = 0
    return result


def getUnixTimestamp(secondsIntoTheFuture=None):
    """
    Returns a Unix time stamp (seconds passed since January 1 1970) for NOW as
    an integer.

    Optionally, pass secondsIntoTheFuture: positive int's will result in a
    future timestamp, negative the past
    """
    if secondsIntoTheFuture:
        future = datetime.utcnow() + timedelta(seconds=secondsIntoTheFuture)
    else:
        future = datetime.utcnow()
    return timegm(future.timetuple())


def kodiSQL(media_type="video"):

    if media_type == "emby":
        dbPath = tryDecode(xbmc.translatePath("special://database/emby.db"))
    elif media_type == "music":
        dbPath = getKodiMusicDBPath()
    elif media_type == "texture":
        dbPath = tryDecode(xbmc.translatePath(
            "special://database/Textures13.db"))
    else:
        dbPath = getKodiVideoDBPath()

    connection = sqlite3.connect(dbPath, timeout=15.0)
    return connection

def getKodiVideoDBPath():

    dbVersion = {

        "13": 78,   # Gotham
        "14": 90,   # Helix
        "15": 93,   # Isengard
        "16": 99,   # Jarvis
        "17": 107,  # Krypton
        "18": 107   # L*****
    }

    dbPath = tryDecode(xbmc.translatePath(
        "special://database/MyVideos%s.db"
        % dbVersion.get(xbmc.getInfoLabel('System.BuildVersion')[:2], "")))
    return dbPath


def create_actor_db_index():
    """
    Index the "actors" because we got a TON - speed up SELECT and WHEN
    """
    conn = kodiSQL('video')
    cursor = conn.cursor()
    try:
        cursor.execute("""
            CREATE UNIQUE INDEX index_name
            ON actor (name);
        """)
    except sqlite3.OperationalError:
        # Index already exists
        pass
    conn.commit()
    conn.close()


def getKodiMusicDBPath():

    dbVersion = {

        "13": 46,   # Gotham
        "14": 48,   # Helix
        "15": 52,   # Isengard
        "16": 56,   # Jarvis
        "17": 60,   # Krypton
        "18": 60    # L*****
    }

    dbPath = tryDecode(xbmc.translatePath(
        "special://database/MyMusic%s.db"
        % dbVersion.get(xbmc.getInfoLabel('System.BuildVersion')[:2], "")))
    return dbPath

def getScreensaver():
    # Get the current screensaver value
    query = {

        'jsonrpc': "2.0",
        'id': 0,
        'method': "Settings.getSettingValue",
        'params': {

            'setting': "screensaver.mode"
        }
    }
    return json.loads(xbmc.executeJSONRPC(json.dumps(query)))['result']['value']

def setScreensaver(value):
    # Toggle the screensaver
    query = {

        'jsonrpc': "2.0",
        'id': 0,
        'method': "Settings.setSettingValue",
        'params': {

            'setting': "screensaver.mode",
            'value': value
        }
    }
    log.debug("Toggling screensaver: %s %s"
              % (value, xbmc.executeJSONRPC(json.dumps(query))))

def reset():

    dialog = xbmcgui.Dialog()

    if dialog.yesno("Warning", "Are you sure you want to reset your local Kodi database?") == 0:
        return

    # first stop any db sync
    window('plex_shouldStop', value="true")
    count = 10
    while window('plex_dbScan') == "true":
        log.debug("Sync is running, will retry: %s..." % count)
        count -= 1
        if count == 0:
            dialog.ok("Warning", "Could not stop the database from running. Try again.")
            return
        xbmc.sleep(1000)

    # Clean up the playlists
    deletePlaylists()

    # Clean up the video nodes
    deleteNodes()

    # Wipe the kodi databases
    log.info("Resetting the Kodi video database.")
    connection = kodiSQL('video')
    cursor = connection.cursor()
    cursor.execute('SELECT tbl_name FROM sqlite_master WHERE type="table"')
    rows = cursor.fetchall()
    for row in rows:
        tablename = row[0]
        if tablename != "version":
            cursor.execute("DELETE FROM " + tablename)
    connection.commit()
    cursor.close()

    if settings('enableMusic') == "true":
        log.info("Resetting the Kodi music database.")
        connection = kodiSQL('music')
        cursor = connection.cursor()
        cursor.execute('SELECT tbl_name FROM sqlite_master WHERE type="table"')
        rows = cursor.fetchall()
        for row in rows:
            tablename = row[0]
            if tablename != "version":
                cursor.execute("DELETE FROM " + tablename)
        connection.commit()
        cursor.close()

    # Wipe the Plex database
    log.info("Resetting the Plex database.")
    connection = kodiSQL('emby')
    cursor = connection.cursor()
    cursor.execute('SELECT tbl_name FROM sqlite_master WHERE type="table"')
    rows = cursor.fetchall()
    for row in rows:
        tablename = row[0]
        if tablename != "version":
            cursor.execute("DELETE FROM " + tablename)
    cursor.execute('DROP table IF EXISTS emby')
    cursor.execute('DROP table IF EXISTS view')
    connection.commit()
    cursor.close()

    # Offer to wipe cached thumbnails
    resp = dialog.yesno("Warning", "Remove all cached artwork?")
    if resp:
        log.info("Resetting all cached artwork.")
        # Remove all existing textures first
        path = tryDecode(xbmc.translatePath("special://thumbnails/"))
        if xbmcvfs.exists(path):
            allDirs, allFiles = xbmcvfs.listdir(path)
            for dir in allDirs:
                allDirs, allFiles = xbmcvfs.listdir(path+dir)
                for file in allFiles:
                    if os.path.supports_unicode_filenames:
                        xbmcvfs.delete(os.path.join(
                            path + tryDecode(dir),
                            tryDecode(file)))
                    else:
                        xbmcvfs.delete(os.path.join(
                            tryEncode(path) + dir,
                            file))

        # remove all existing data from texture DB
        connection = kodiSQL('texture')
        cursor = connection.cursor()
        cursor.execute('SELECT tbl_name FROM sqlite_master WHERE type="table"')
        rows = cursor.fetchall()
        for row in rows:
            tableName = row[0]
            if(tableName != "version"):
                cursor.execute("DELETE FROM " + tableName)
        connection.commit()
        cursor.close()

    # reset the install run flag
    settings('SyncInstallRunDone', value="false")

    # Remove emby info
    resp = dialog.yesno("Warning", "Reset all Plex KodiConnect Addon settings?")
    if resp:
        # Delete the settings
        addon = xbmcaddon.Addon()
        addondir = tryDecode(xbmc.translatePath(addon.getAddonInfo('profile')))
        dataPath = "%ssettings.xml" % addondir
        xbmcvfs.delete(tryEncode(dataPath))
        log.info("Deleting: settings.xml")

    dialog.ok(
        heading=addonName,
        line1="Database reset has completed, Kodi will now restart to apply the changes.")
    xbmc.executebuiltin('RestartApp')

def profiling(sortby="cumulative"):
    # Will print results to Kodi log
    def decorator(func):
        def wrapper(*args, **kwargs):

            pr = cProfile.Profile()

            pr.enable()
            result = func(*args, **kwargs)
            pr.disable()

            s = StringIO.StringIO()
            ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
            ps.print_stats()
            log.info(s.getvalue())

            return result

        return wrapper
    return decorator

def convertdate(date):
    try:
        date = datetime.strptime(date, "%Y-%m-%dT%H:%M:%SZ")
    except TypeError:
        # TypeError: attribute of type 'NoneType' is not callable
        # Known Kodi/python error
        date = datetime(*(time.strptime(date, "%Y-%m-%dT%H:%M:%SZ")[0:6]))

    return date

def normalize_nodes(text):
    # For video nodes
    text = text.replace(":", "")
    text = text.replace("/", "-")
    text = text.replace("\\", "-")
    text = text.replace("<", "")
    text = text.replace(">", "")
    text = text.replace("*", "")
    text = text.replace("?", "")
    text = text.replace('|', "")
    text = text.replace('(', "")
    text = text.replace(')', "")
    text = text.strip()
    # Remove dots from the last character as windows can not have directories
    # with dots at the end
    text = text.rstrip('.')
    text = tryEncode(unicodedata.normalize('NFKD', unicode(text, 'utf-8')))

    return text

def normalize_string(text):
    # For theme media, do not modify unless
    # modified in TV Tunes
    text = text.replace(":", "")
    text = text.replace("/", "-")
    text = text.replace("\\", "-")
    text = text.replace("<", "")
    text = text.replace(">", "")
    text = text.replace("*", "")
    text = text.replace("?", "")
    text = text.replace('|', "")
    text = text.strip()
    # Remove dots from the last character as windows can not have directories
    # with dots at the end
    text = text.rstrip('.')
    text = tryEncode(unicodedata.normalize('NFKD', unicode(text, 'utf-8')))

    return text

def indent(elem, level=0):
    # Prettify xml trees
    i = "\n" + level*"  "
    if len(elem):
        if not elem.text or not elem.text.strip():
          elem.text = i + "  "
        if not elem.tail or not elem.tail.strip():
          elem.tail = i
        for elem in elem:
          indent(elem, level+1)
        if not elem.tail or not elem.tail.strip():
          elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
          elem.tail = i


def guisettingsXML():
    """
    Returns special://userdata/guisettings.xml as an etree xml root element
    """
    path = tryDecode(xbmc.translatePath("special://profile/"))
    xmlpath = "%sguisettings.xml" % path

    try:
        xmlparse = etree.parse(xmlpath)
    except:
        # Document is blank or missing
        root = etree.Element('settings')
    else:
        root = xmlparse.getroot()
    return root


def __setXMLTag(element, tag, value, attrib=None):
    """
    Looks for an element's subelement and sets its value.
    If "subelement" does not exist, create it using attrib and value.

        element : etree element
        tag     : string/unicode for subelement
        value   : string/unicode
        attrib  : dict; will use etree attrib method

    Returns the subelement
    """
    subelement = element.find(tag)
    if subelement is None:
        # Setting does not exist yet; create it
        if attrib is None:
            etree.SubElement(element, tag).text = value
        else:
            etree.SubElement(element, tag, attrib=attrib).text = value
    else:
        subelement.text = value
    return subelement


def __setSubElement(element, subelement):
    """
    Returns an etree element's subelement. Creates one if not exist
    """
    answ = element.find(subelement)
    if answ is None:
        answ = etree.SubElement(element, subelement)
    return answ


def advancedSettingsXML():
    """
    Kodi tweaks

    Changes advancedsettings.xml, musiclibrary:
        backgroundupdate        set to "true"

    Overrides guisettings.xml in Kodi userdata folder:
        updateonstartup  : set to "false"
        usetags          : set to "false"
        findremotethumbs : set to "false"
    """
    path = tryDecode(xbmc.translatePath("special://profile/"))
    xmlpath = "%sadvancedsettings.xml" % path

    try:
        xmlparse = etree.parse(xmlpath)
    except:
        # Document is blank or missing
        root = etree.Element('advancedsettings')
    else:
        root = xmlparse.getroot()

    music = __setSubElement(root, 'musiclibrary')
    __setXMLTag(music, 'backgroundupdate', "true")
    # __setXMLTag(music, 'updateonstartup', "false")

    # Subtag 'musicfiles'
    # music = __setSubElement(root, 'musicfiles')
    # __setXMLTag(music, 'usetags', "false")
    # __setXMLTag(music, 'findremotethumbs', "false")

    # Prettify and write to file
    try:
        indent(root)
    except:
        pass
    etree.ElementTree(root).write(xmlpath)


def sourcesXML():
    # To make Master lock compatible
    path = tryDecode(xbmc.translatePath("special://profile/"))
    xmlpath = "%ssources.xml" % path

    try:
        xmlparse = etree.parse(xmlpath)
    except: # Document is blank or missing
        root = etree.Element('sources')
    else:
        root = xmlparse.getroot()


    video = root.find('video')
    if video is None:
        video = etree.SubElement(root, 'video')
        etree.SubElement(video, 'default', attrib={'pathversion': "1"})

    # Add elements
    count = 2
    for source in root.findall('.//path'):
        if source.text == "smb://":
            count -= 1

        if count == 0:
            # sources already set
            break
    else:
        # Missing smb:// occurences, re-add.
        for i in range(0, count):
            source = etree.SubElement(video, 'source')
            etree.SubElement(source, 'name').text = "Plex"
            etree.SubElement(source, 'path', attrib={'pathversion': "1"}).text = "smb://"
            etree.SubElement(source, 'allowsharing').text = "true"
    # Prettify and write to file
    try:
        indent(root)
    except: pass
    etree.ElementTree(root).write(xmlpath)


def passwordsXML():
    # To add network credentials
    path = tryDecode(xbmc.translatePath("special://userdata/"))
    xmlpath = "%spasswords.xml" % path

    try:
        xmlparse = etree.parse(xmlpath)
    except: # Document is blank or missing
        root = etree.Element('passwords')
        skipFind = True
    else:
        root = xmlparse.getroot()
        skipFind = False

    dialog = xbmcgui.Dialog()
    credentials = settings('networkCreds')
    if credentials:
        # Present user with options
        option = dialog.select(
            "Modify/Remove network credentials", ["Modify", "Remove"])

        if option < 0:
            # User cancelled dialog
            return

        elif option == 1:
            # User selected remove
            for paths in root.getiterator('passwords'):
                for path in paths:
                    if path.find('.//from').text == "smb://%s/" % credentials:
                        paths.remove(path)
                        log.info("Successfully removed credentials for: %s"
                                 % credentials)
                        etree.ElementTree(root).write(xmlpath)
                        break
            else:
                log.error("Failed to find saved server: %s in passwords.xml"
                          % credentials)

            settings('networkCreds', value="")
            xbmcgui.Dialog().notification(
                heading='PlexKodiConnect',
                message="%s removed from passwords.xml" % credentials,
                icon="special://home/addons/plugin.video.plexkodiconnect/icon.png",
                time=1000,
                sound=False)
            return

        elif option == 0:
            # User selected to modify
            server = dialog.input("Modify the computer name or ip address", credentials)
            if not server:
                return
    else:
        # No credentials added
        dialog.ok(
            heading="Network credentials",
            line1= (
                "Input the server name or IP address as indicated in your plex library paths. "
                'For example, the server name: \\\\SERVER-PC\\path\\ or smb://SERVER-PC/path is "SERVER-PC".'))
        server = dialog.input("Enter the server name or IP address")
        if not server:
            return

    # Network username
    user = dialog.input("Enter the network username")
    if not user:
        return
    # Network password
    password = dialog.input("Enter the network password",
                            '',  # Default input
                            xbmcgui.INPUT_ALPHANUM,
                            xbmcgui.ALPHANUM_HIDE_INPUT)
    # Need to url-encode the password
    from urllib import quote_plus
    password = quote_plus(password)
    # Add elements. Annoying etree bug where findall hangs forever
    if skipFind is False:
        skipFind = True
        for path in root.findall('.//path'):
            if path.find('.//from').text.lower() == "smb://%s/" % server.lower():
                # Found the server, rewrite credentials
                path.find('.//to').text = "smb://%s:%s@%s/" % (user, password, server)
                skipFind = False
                break
    if skipFind:
        # Server not found, add it.
        path = etree.SubElement(root, 'path')
        etree.SubElement(path, 'from', attrib={'pathversion': "1"}).text = "smb://%s/" % server
        topath = "smb://%s:%s@%s/" % (user, password, server)
        etree.SubElement(path, 'to', attrib={'pathversion': "1"}).text = topath
        # Force Kodi to see the credentials without restarting
        xbmcvfs.exists(topath)

    # Add credentials
    settings('networkCreds', value="%s" % server)
    log.info("Added server: %s to passwords.xml" % server)
    # Prettify and write to file
    try:
        indent(root)
    except: pass
    etree.ElementTree(root).write(xmlpath)

    # dialog.notification(
    #     heading="PlexKodiConnect",
    #     message="Added to passwords.xml",
    #     icon="special://home/addons/plugin.video.plexkodiconnect/icon.png",
    #     time=5000,
    #     sound=False)

def playlistXSP(mediatype, tagname, viewid, viewtype="", delete=False):
    """
    Feed with tagname as unicode
    """
    path = tryDecode(xbmc.translatePath("special://profile/playlists/video/"))
    if viewtype == "mixed":
        plname = "%s - %s" % (tagname, mediatype)
        xsppath = "%sPlex %s - %s.xsp" % (path, viewid, mediatype)
    else:
        plname = tagname
        xsppath = "%sPlex %s.xsp" % (path, viewid)

    # Create the playlist directory
    if not xbmcvfs.exists(tryEncode(path)):
        log.info("Creating directory: %s" % path)
        xbmcvfs.mkdirs(tryEncode(path))

    # Only add the playlist if it doesn't already exists
    if xbmcvfs.exists(tryEncode(xsppath)):
        log.info('Path %s does exist' % xsppath)
        if delete:
            xbmcvfs.delete(tryEncode(xsppath))
            log.info("Successfully removed playlist: %s." % tagname)

        return

    # Using write process since there's no guarantee the xml declaration works with etree
    itemtypes = {
        'homevideos': 'movies',
        'movie': 'movies',
        'show': 'tvshows'
    }
    log.info("Writing playlist file to: %s" % xsppath)
    try:
        f = xbmcvfs.File(tryEncode(xsppath), 'wb')
    except:
        log.error("Failed to create playlist: %s" % xsppath)
        return
    else:
        f.write(tryEncode(
            '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>\n'
            '<smartplaylist type="%s">\n\t'
                '<name>Plex %s</name>\n\t'
                '<match>all</match>\n\t'
                '<rule field="tag" operator="is">\n\t\t'
                    '<value>%s</value>\n\t'
                '</rule>\n'
            '</smartplaylist>\n'
            % (itemtypes.get(mediatype, mediatype), plname, tagname)))
        f.close()
    log.info("Successfully added playlist: %s" % tagname)

def deletePlaylists():

    # Clean up the playlists
    path = tryDecode(xbmc.translatePath("special://profile/playlists/video/"))
    dirs, files = xbmcvfs.listdir(tryEncode(path))
    for file in files:
        if tryDecode(file).startswith('Plex'):
            xbmcvfs.delete(tryEncode("%s%s" % (path, tryDecode(file))))

def deleteNodes():

    # Clean up video nodes
    import shutil
    path = tryDecode(xbmc.translatePath("special://profile/library/video/"))
    dirs, files = xbmcvfs.listdir(tryEncode(path))
    for dir in dirs:
        if tryDecode(dir).startswith('Plex'):
            try:
                shutil.rmtree("%s%s" % (path, tryDecode(dir)))
            except:
                log.error("Failed to delete directory: %s" % tryDecode(dir))
    for file in files:
        if tryDecode(file).startswith('plex'):
            try:
                xbmcvfs.delete(tryEncode("%s%s" % (path, tryDecode(file))))
            except:
                log.error("Failed to file: %s" % tryDecode(file))


###############################################################################
# WRAPPERS

def CatchExceptions(warnuser=False):
    """
    Decorator for methods to catch exceptions and log them. Useful for e.g.
    librarysync threads using itemtypes.py, because otherwise we would not
    get informed of crashes

    warnuser=True:      sets the window flag 'plex_scancrashed' to true
                        which will trigger a Kodi infobox to inform user
    """
    def decorate(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                log.error('%s has crashed. Error: %s' % (func.__name__, e))
                import traceback
                log.error("Traceback:\n%s" % traceback.format_exc())
                if warnuser:
                    window('plex_scancrashed', value='true')
                return
        return wrapper
    return decorate


def LogTime(func):
    """
    Decorator for functions and methods to log the time it took to run the code
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        starttotal = datetime.now()
        result = func(*args, **kwargs)
        elapsedtotal = datetime.now() - starttotal
        log.debug('It took %s to run the function %s'
                  % (elapsedtotal, func.__name__))
        return result
    return wrapper


def ThreadMethodsAdditionalStop(windowAttribute):
    """
    Decorator to replace stopThread method to include the Kodi windowAttribute

    Use with any sync threads. @ThreadMethods still required FIRST
    """
    def wrapper(cls):
        def threadStopped(self):
            return (self._threadStopped or
                    (window('plex_terminateNow') == "true") or
                    window(windowAttribute) == "true")
        cls.threadStopped = threadStopped
        return cls
    return wrapper


def ThreadMethodsAdditionalSuspend(windowAttribute):
    """
    Decorator to replace threadSuspended(): thread now also suspends if a
    Kodi windowAttribute is set to 'true', e.g. 'suspend_LibraryThread'

    Use with any library sync threads. @ThreadMethods still required FIRST
    """
    def wrapper(cls):
        def threadSuspended(self):
            return (self._threadSuspended or
                    window(windowAttribute) == 'true')
        cls.threadSuspended = threadSuspended
        return cls
    return wrapper


def ThreadMethods(cls):
    """
    Decorator to add the following methods to a threading class:

    suspendThread():    pauses the thread
    resumeThread():     resumes the thread
    stopThread():       stopps/kills the thread

    threadSuspended():  returns True if thread is suspend_thread
    threadStopped():    returns True if thread is stopped (or should stop ;-))
                        ALSO stops if Kodi is exited

    Also adds the following class attributes:
        _threadStopped
        _threadSuspended
    """
    # Attach new attributes to class
    cls._threadStopped = False
    cls._threadSuspended = False

    # Define new class methods and attach them to class
    def stopThread(self):
        self._threadStopped = True
    cls.stopThread = stopThread

    def suspendThread(self):
        self._threadSuspended = True
    cls.suspendThread = suspendThread

    def resumeThread(self):
        self._threadSuspended = False
    cls.resumeThread = resumeThread

    def threadSuspended(self):
        return self._threadSuspended
    cls.threadSuspended = threadSuspended

    def threadStopped(self):
        return self._threadStopped or (window('plex_terminateNow') == 'true')
    cls.threadStopped = threadStopped

    # Return class to render this a decorator
    return cls


###############################################################################
# UNUSED METHODS

def changePlayState(itemType, kodiId, playCount, lastplayed):
    """
    YET UNUSED

    kodiId: int or str
    playCount: int or str
    lastplayed: str or int unix timestamp
    """
    lastplayed = DateToKodi(lastplayed)

    kodiId = int(kodiId)
    playCount = int(playCount)
    method = {
        'movie': ' VideoLibrary.SetMovieDetails',
        'episode': 'VideoLibrary.SetEpisodeDetails',
        'musicvideo': ' VideoLibrary.SetMusicVideoDetails',  # TODO
        'show': 'VideoLibrary.SetTVShowDetails',  # TODO
        '': 'AudioLibrary.SetAlbumDetails',  # TODO
        '': 'AudioLibrary.SetArtistDetails',  # TODO
        'track': 'AudioLibrary.SetSongDetails'
    }
    params = {
        'movie': {
            'movieid': kodiId,
            'playcount': playCount,
            'lastplayed': lastplayed
        },
        'episode': {
            'episodeid': kodiId,
            'playcount': playCount,
            'lastplayed': lastplayed
        }
    }
    query = {
        "jsonrpc": "2.0",
        "id": 1,
    }
    query['method'] = method[itemType]
    query['params'] = params[itemType]
    result = xbmc.executeJSONRPC(json.dumps(query))
    result = json.loads(result)
    result = result.get('result')
    log.debug("JSON result was: %s" % result)
