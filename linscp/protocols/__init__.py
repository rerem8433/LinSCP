from .base import Cancelled, Entry, RemoteFS, Site

PROTOCOLS = ["sftp", "scp", "ftp", "ftps", "ftps-implicit"]
PROTOCOL_LABELS = {
    "sftp": "SFTP",
    "scp": "SCP",
    "ftp": "FTP",
    "ftps": "FTPS (explicite)",
    "ftps-implicit": "FTPS (implicite)",
}


def make_fs(site: Site, trust_cb=None) -> RemoteFS:
    if site.protocol == "sftp":
        from .sftp import SFTPFS
        return SFTPFS(site, trust_cb)
    if site.protocol == "scp":
        from .scp import SCPFS
        return SCPFS(site, trust_cb)
    from .ftp import FTPFS
    return FTPFS(site, trust_cb)


__all__ = ["Cancelled", "Entry", "RemoteFS", "Site", "PROTOCOLS", "PROTOCOL_LABELS", "make_fs"]
