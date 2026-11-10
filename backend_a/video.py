"""Validate the container, codec and duration of an uploaded recording."""

from io import BytesIO

from backend_a.errors import ApiError, require

RECORDING_FORMATS = {
    "video/mp4": ("mp4", ("h264", "hevc", "vp9", "av1")),
    "video/webm": ("webm", ("vp8", "vp9", "av1")),
}


def validate_video(data: bytes, content_type: str, max_seconds: float):
    import av

    header_ok = (content_type == "video/webm" and data.startswith(b"\x1a\x45\xdf\xa3")) or (
        content_type == "video/mp4" and len(data) >= 12 and data[4:8] == b"ftyp"
    )
    require(header_ok, "UNSUPPORTED_MEDIA_TYPE", 400, "録画の形式を確認してください")
    demuxer, codecs = RECORDING_FORMATS[content_type]
    try:
        # FFmpeg can open decoders during av.open() to find stream info.
        # The AV1 probe can use libdav1d, whose canonical codec name is av1.
        with av.open(
            BytesIO(data),
            format=demuxer,
            container_options={"codec_whitelist": ",".join((*codecs, "libdav1d"))},
        ) as container:
            streams = list(container.streams.video)
            if len(streams) != 1:
                raise ValueError("One video stream required")
            stream = streams[0]
            codec = stream.codec_context
            if codec is None or codec.codec.canonical_name not in codecs:
                raise ValueError("Unsupported video codec")
            # Do not decode arbitrary resolution/unbounded frames into memory.
            if codec.width * codec.height > 1920 * 1080:
                raise ApiError("PAYLOAD_TOO_LARGE", 400, "録画の解像度が大きすぎます")
            duration = 0.0
            frames = 0
            for packet in container.demux(stream):
                if packet.pts is not None and packet.time_base is not None:
                    duration = max(
                        duration, float((packet.pts + (packet.duration or 0)) * packet.time_base)
                    )
                frames += 1
                if duration > max_seconds + 0.5 or frames > 120 * (max_seconds + 1):
                    raise ApiError("PAYLOAD_TOO_LARGE", 400, "録画の時間が長すぎます")
            if duration <= 0 or frames < 2:
                raise ValueError("No timed video packets")
    except ApiError:
        raise
    except (av.FFmpegError, ValueError, OverflowError) as exc:
        raise ApiError("UNSUPPORTED_MEDIA_TYPE", 400, "録画を読み取れません") from exc
