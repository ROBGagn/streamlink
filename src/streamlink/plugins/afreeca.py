import re

from streamlink.plugin import Plugin
from streamlink.plugin.api import http, validate
from streamlink.stream import RTMPStream, HLSStream

CHANNEL_API_URL = "http://live.afreecatv.com:8057/afreeca/player_live_api.php"
STREAM_INFO_URLS = "{rmd}/broad_stream_assign.html"

CHANNEL_RESULT_ERROR = 0
CHANNEL_RESULT_OK = 1

QUALITYS=["original", "hd", "sd"]

QUALITY_WEIGHTS = {
    "original": 1080,
    "hd": 720,
    "sd": 480
}

_url_re = re.compile(r"http(s)?://(?P<cdn>\w+\.)?afreeca(tv)?.com/(?P<username>\w+)(/\d+)?")

_channel_schema = validate.Schema(
    {
        "CHANNEL": {
            "RESULT": validate.transform(int),
            validate.optional("BNO"): validate.text,
            validate.optional("RMD"): validate.text,
            validate.optional("AID"): validate.text,
            validate.optional("CDN"): validate.text
        }
    },
    validate.get("CHANNEL")
)

_stream_schema = validate.Schema(
    {
        validate.optional("view_url"): validate.url(
            scheme=validate.any("rtmp", "http")
        ),
        "stream_status": validate.text
    }
)

class AfreecaTV(Plugin):
    @classmethod
    def can_handle_url(self, url):
        return _url_re.match(url)

    @classmethod
    def stream_weight(cls, key):
        weight = QUALITY_WEIGHTS.get(key)
        if weight:
            return weight, "afreeca"

        return Plugin.stream_weight(key)

    def _get_channel_info(self, username):
        data = {
            "bid": username,
            "mode": "landing",
            "player_type": "html5"
        }

        res = http.post(CHANNEL_API_URL, data=data)
        return http.json(res, schema=_channel_schema)

    def _get_hls_key(self, broadcast, username, quality):
        headers = {
            "Referer": self.url
        }

        data = {
            "bid": username,
            "bno": broadcast,
            "pwd": "",
            "quality": quality,
            "type": "pwd"
        }
        res = http.post(CHANNEL_API_URL, data=data, headers=headers)
        return http.json(res, schema=_channel_schema)

    def _get_stream_info(self, broadcast, quality, cdn, rmd):
        params={
            "return_type": cdn,
            "broad_key": "{broadcast}-flash-{quality}-hls".format(**locals())
        }
        res = http.get(STREAM_INFO_URLS.format(rmd=rmd), params=params)
        return http.json(res, schema=_stream_schema)

    def _get_hls_stream(self, broadcast, username, quality, cdn, rmd):
        keyjson = self._get_hls_key(broadcast, username, quality)

        if keyjson["RESULT"] != CHANNEL_RESULT_OK:
            return
        key = keyjson["AID"]

        info = self._get_stream_info(broadcast, quality, cdn, rmd)

        if "view_url" in info:
            return HLSStream(self.session, info["view_url"], params=dict(aid=key))


    def _get_streams(self):
        match = _url_re.match(self.url)
        username = match.group("username")

        channel = self._get_channel_info(username)
        if channel["RESULT"] != CHANNEL_RESULT_OK:
            return

        (broadcast, rmd, cdn) = (channel["BNO"], channel["RMD"], channel["CDN"])
        if not (broadcast and rmd and cdn):
            return

        for qkey in QUALITYS:
            hls_stream = self._get_hls_stream(broadcast, username, qkey, cdn, rmd)
            if hls_stream:
                yield qkey, hls_stream

__plugin__ = AfreecaTV
