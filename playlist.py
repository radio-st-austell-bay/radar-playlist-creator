# Dependencies:
# gdata
# pylast
# spotipy
# requests

_config = None
def get_config():
    import ConfigParser
    import os.path
    global _config
    if _config is None:
        fname = os.path.normpath(os.path.abspath(
            os.path.join(__file__, '..', 'config.ini')
        ))
        if not os.path.exists(fname):
            print 'Config file not found: %s' % (fname,)
        else:
            _config = ConfigParser.SafeConfigParser()
            _config.read(fname)
    return _config


# XXX make this configurable
def _make_playlist_name(details):
    return 'Radar %3.3d: %s' % (details['number'], details['date'])


def get_playlist_from_google(show_number):
    from gdata.spreadsheet.service import SpreadsheetsService, ListQuery
    config = get_config()
    key = config.get('google', 'sheet_key')
    client = SpreadsheetsService()
    feed = client.GetWorksheetsFeed(
        key,
        visibility='public',
        projection='basic',
    )
    shows_sheet_id = tracks_sheet_id = None
    for sheet in feed.entry:
        compare = sheet.title.text.lower()
        sheet_id = sheet.id.text.rsplit('/', 1)[1]
        if compare == 'shows':
            shows_sheet_id = sheet_id
        elif compare == 'playlists':
            tracks_sheet_id = sheet_id
    if shows_sheet_id is None:
        print 'Shows worksheet not found'
    if tracks_sheet_id is None:
        print 'Playlists worksheet not found'
    if shows_sheet_id is None or tracks_sheet_id is None:
        return None

    query = ListQuery()
    query.sq = 'shownumber = %s' % (show_number,)
    feed = client.GetListFeed(
        key,
        wksht_id=shows_sheet_id,
        visibility='public',
        projection='full',
        query=query,
    )
    retrieved_details = feed.entry[0]
    details = {
        'number': show_number,
        'id': retrieved_details.custom['showid'].text,
        'date': retrieved_details.custom['showdate'].text,
        'title': retrieved_details.custom['title'].text,
        'notes': retrieved_details.custom['notes'].text,
        'tracks': [],
    }

    query = ListQuery()
    # XXX _cn6ca is obviously magic.  How do I get it properly?
    query.sq = '_cn6ca = %s' % (details['id'],)
    feed = client.GetListFeed(
        key,
        wksht_id=tracks_sheet_id,
        visibility='public',
        projection='full',
        query=query,
    )
    for item in feed.entry:
        details['tracks'].append({
            'number': int(item.custom['tracknumber'].text),
            'album': item.custom['album'].text,
            'artist': item.custom['artist'].text,
            'title': item.custom['songtitle'].text,
            'version': item.custom['songversion'].text,
        })

    details['tracks'].sort(key=lambda t: t['number'])
    return details


def add_to_lastfm(details):
    import pylast
    config = get_config()
    username = config.get('lastfm', 'username')
    password_hash = config.get('lastfm', 'password_hash')
    if password_hash is None:
        password_hash = pylast.md5(config.get('lastfm', 'password'))
    conn = pylast.LastFMNetwork(
        api_key=config.get('lastfm', 'api_key'),
        api_secret=config.get('lastfm', 'api_secret'),
        username=config.get('lastfm', 'username'),
        password_hash=password_hash,
    )

    # raise NotImplementedError('Try with 17 -- maybe an encoding error with &?')

    playlist_name = _make_playlist_name(details)
    description_elements = []
    if details.get('title'):
        description_elements.append(details['title'])
    if details.get('notes'):
        description_elements.append(details['notes'])
    existing_playlists = conn.get_user(username).get_playlists()
    for p in existing_playlists:
        if p.get_title() == playlist_name:
            print 'Already have last.fm playlist', playlist_name
            return False

    playlist = conn.create_new_playlist(
        playlist_name,
        ': '.join(description_elements),
    )

    for track_details in details['tracks']:
        track_title = track_details['title']
        if track_details.get('version'):
            track_title = '%s (%s)' % (track_title, track_details['version'])
        track = pylast.Track(
            track_details['artist'],
            track_title,
            conn,
        )
        try:
            playlist.add_track(track)
        except pylast.WSError, e:
            print 'Show %s (ID: %s), track %s (%s, %s): error: %s' % (
                details['number'],
                details['id'],
                track_details.get('number'),
                track_details['artist'],
                track_title,
                e,
            )
            print 'Skipping remaining tracks'
            return False

    print 'Created last.fm playlist:', playlist_name
    return True


_sp = None


def add_to_spotify(details):
    global _sp
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials
    from spotipy.util import prompt_for_user_token
    config = get_config()
    user_id = config.get('spotify', 'user_id')
    # https://github.com/plamere/spotipy
    # https://developer.spotify.com/web-api/playlist-endpoints/
    if _sp is None:
        scope = 'playlist-modify-public'
        token = prompt_for_user_token(
            user_id,
            scope=' '.join([
                'playlist-modify-public',
            ]),
            client_id=config.get('spotify', 'client_id'),
            client_secret=config.get('spotify', 'client_secret'),
            redirect_uri=config.get('spotify', 'redirect_uri'),
        )
        if not token:
            raise RuntimeError("no auth")
        _sp = spotipy.Spotify(auth=token)
    sp_create = _sp
    sp_search = spotipy.Spotify(
        client_credentials_manager=SpotifyClientCredentials(
            client_id=config.get('spotify', 'client_id'),
            client_secret=config.get('spotify', 'client_secret'),
        ),
    )

    playlists = sp_create.user_playlists(user_id)
    if 1: playlists = []
    while playlists:
        for i, playlist in enumerate(playlists['items']):
            # Uncomment these two to clear all playlists:
            # sp_create.user_playlist_change_details(user_id, playlist['id'], name='DELETE ME')
            # sp_create.user_playlist_replace_tracks(user_id, playlist['id'], [])
            print("%4d %s %s" % (i + 1 + playlists['offset'], playlist['uri'],  playlist['name']))
        if playlists['next']:
            playlists = sp_create.next(playlists)
        else:
            playlists = None

    import pprint
    # pprint.pprint(details)
    def _run_serch(artist, title, album, version):
        qdict = {}
        if artist:
            qdict['artist'] = artist
        if title:
            if version:
                title = '%s (%s)' % (title, version)
            qdict['track'] = title
        if album:
            qdict['album'] = album
        result = sp_search.search(
            ' '.join('%s:"%s"' % (k, qdict[k]) for k in qdict),
            type='track',
        )
        if result['tracks']['items']:
            return result['tracks']['items'][0]['id']
        return None

    def _search_for(track_details):
        artist = track_details['artist']
        title = track_details['title']
        album = track_details['album']
        version = track_details['version']
        for criteria in [
            (artist, title, album, version),
            (artist, title, None, version),
            (artist, title, album, None),
            (artist, title, None, None),
        ]:
            track_id = _run_serch(*criteria)
            if track_id is not None:
                return track_id
        return None

    track_ids = []
    for track_details in details['tracks']:
        tid = _search_for(track_details)
        if tid is None:
            print "Didn't add:", track_details
        else:
            track_ids.append(tid)

    playlist_name = _make_playlist_name(details)
    playlist_details = sp_create.user_playlist_create(
        user_id,
        _make_playlist_name(details),
    )
    sp_create.user_playlist_add_tracks(
        user_id,
        playlist_details['id'],
        track_ids,
    )
    # XXX need a way to modify playlist through web or app, so I can fix small
    # errors.
    print 'Created playlist', playlist_details['id'], playlist_details['name']



if __name__ == '__main__':
    import sys
    import time

    argv = sys.argv[1:]
    opt_lastfm = None
    opt_spotify = None
    if '-l' in argv:
        opt_lastfm = True
        while '-l' in argv:
            argv.remove('-l')
    if '-s' in argv:
        opt_spotify = True
        while '-s' in argv:
            argv.remove('-s')
    if opt_lastfm is None and opt_spotify is None:
        opt_lastfm = True
        opt_spotify = True
    if opt_lastfm is None:
        opt_lastfm = False
    if opt_spotify is None:
        opt_spotify = False

    if len(argv) == 0:
        print "Usage: %s SHOW_NUMBER [END_SHOW_NUMBER]" % (sys.argv[0],)
        sys.exit(1)

    config = get_config()
    if config is None:
        sys.exit(1)

    show_number = int(argv[0])
    if len(argv) > 1:
        shows = range(show_number, int(argv[1])+1)
    else:
        shows = [show_number]
    for n in shows:
        details = get_playlist_from_google(n)
        if details is None:
            continue
        if opt_lastfm:
            if not add_to_lastfm(details):
                print 'Stopping due to error'
                break
        if opt_spotify:
            if not add_to_spotify(details):
                print 'Stopping due to error'
                break

# Missing tracks:
#   50, Just Plain Ant
# Next (when Alex has sorted himself out):
# python playlist.py -l 88 276
