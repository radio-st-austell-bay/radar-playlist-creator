
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


def get_all_playlist_numbers_from_google():
    from gdata.spreadsheet.service import SpreadsheetsService, ListQuery
    config = get_config()
    key = config.get('google', 'sheet_key')
    client = SpreadsheetsService()
    feed = client.GetWorksheetsFeed(
        key,
        visibility='public',
        projection='basic',
    )
    shows_sheet_id = None
    for sheet in feed.entry:
        compare = sheet.title.text.lower()
        sheet_id = sheet.id.text.rsplit('/', 1)[1]
        if compare == 'shows':
            shows_sheet_id = sheet_id
            break
    if shows_sheet_id is None:
        print 'Shows worksheet not found'
        return None

    feed = client.GetListFeed(
        key,
        wksht_id=shows_sheet_id,
        visibility='public',
        projection='full',
    )
    show_numbers = {}
    for item in feed.entry:
        show_numbers[int(item.custom['showid'].text)] = (
            int(item.custom['shownumber'].text)
            if item.custom['shownumber'].text is not None
            else None
        )
    return show_numbers


_sp = None

def get_spotify_details(show_numbers):
    global _sp
    import os
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
    sp_read = _sp

    playlists = {}
    results = sp_read.user_playlists(user_id)
    while True:
        for playlist in results['items']:
            playlists[int(playlist['name'].strip().split()[1])] = playlist['id']
        if not results['next']:
            break
        results = sp_read.next(results)

    result = []
    for show_id in sorted(show_numbers):
        show_number = show_numbers[show_id]
        playlist_id = playlists.get(show_number)
        if playlist_id is None:
            show_number = playlist_id = ''
        result.append(playlist_id)
        # result.append('%d,%d,%s' % (show_id, show_number, playlist_id))
    return '\n'.join(result)


if __name__ == '__main__':
    import sys
    import time

    config = get_config()
    if config is None:
        sys.exit(1)

    print get_spotify_details(get_all_playlist_numbers_from_google())
