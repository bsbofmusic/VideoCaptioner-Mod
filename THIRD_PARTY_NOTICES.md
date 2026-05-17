# Third Party Notices

This project is based on [WEIFENG2333/VideoCaptioner](https://github.com/WEIFENG2333/VideoCaptioner) and remains licensed under GPL-3.0.

The project depends on multiple third-party components. Their licenses are governed by their respective upstream projects. Common dependencies include, but are not limited to:

- PyQt5 / Qt
- PyQt-Fluent-Widgets
- requests
- httpx
- openai Python SDK
- diskcache
- yt-dlp
- json-repair
- pydub
- tenacity
- Pillow
- fonttools
- platformdirs
- modelscope
- psutil
- GPUtil

The bundled font under `videocaptioner/resources/fonts/` is provided by its upstream license. Users redistributing binaries should verify and include all applicable font notices.

If redistributing binaries with FFmpeg or other external executables, include their corresponding licenses, build information, and source-code access notices as required by their licenses.

Do not redistribute API keys, private configuration files, logs, caches, generated subtitles, generated media, or user data.

## Binary distribution notes

Windows installer builds may bundle `ffmpeg.exe` obtained through the `imageio-ffmpeg` Python package for local media processing. FFmpeg is distributed by its upstream project under its own license terms. Source code and license information are available from <https://ffmpeg.org/> and <https://github.com/imageio/imageio-ffmpeg>.
