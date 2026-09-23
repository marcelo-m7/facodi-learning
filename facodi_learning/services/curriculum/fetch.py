import ipaddress
import socket
import urllib.error
import urllib.request
from urllib.parse import urljoin, urlparse


DEFAULT_TIMEOUT = 15
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_ALLOWED_HOSTS = frozenset({"ualg.pt", "www.ualg.pt"})


class CurriculumFetchError(RuntimeError):
    pass


def _validate_url(url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS:
        raise CurriculumFetchError("Curriculum URL is outside the official provider allowlist.")
    if parsed.username or parsed.password or parsed.port not in (None, 443):
        raise CurriculumFetchError("Curriculum URL contains forbidden authority data.")
    if not re_course_plan_path(parsed.path):
        raise CurriculumFetchError("Curriculum URL is not an allowed UAlg course-plan path.")
    return parsed


def re_course_plan_path(path):
    parts = [part for part in path.split("/") if part]
    return len(parts) == 3 and parts[0] in {"curso", "pt", "en"} and (
        (parts[0] == "curso" and parts[2] == "plano")
        or (parts[0] in {"pt", "en"} and parts[1] == "curso")
    ) or len(parts) == 4 and parts[0] in {"pt", "en"} and parts[1] == "curso" and parts[3] == "plano"


def _validate_public_resolution(hostname):
    try:
        addresses = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    except OSError as error:
        raise CurriculumFetchError("Official curriculum host could not be resolved.") from error
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise CurriculumFetchError("Official curriculum host resolved to a non-public address.")


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        target = urljoin(request.full_url, newurl)
        _validate_url(target)
        return super().redirect_request(request, fp, code, msg, headers, target)


def fetch_official_curriculum(url, *, timeout=DEFAULT_TIMEOUT, max_bytes=MAX_RESPONSE_BYTES):
    parsed = _validate_url(url)
    _validate_public_resolution(parsed.hostname)
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": "FACODI curriculum verifier/1.0 (+https://facodi.com)",
        },
    )
    opener = urllib.request.build_opener(_SafeRedirectHandler())
    try:
        with opener.open(request, timeout=timeout) as response:
            final_url = response.geturl()
            _validate_url(final_url)
            content_type = response.headers.get_content_type()
            if content_type not in {"text/html", "application/xhtml+xml"}:
                raise CurriculumFetchError("Official curriculum response is not HTML.")
            raw = response.read(max_bytes + 1)
    except CurriculumFetchError:
        raise
    except (OSError, urllib.error.URLError, urllib.error.HTTPError) as error:
        raise CurriculumFetchError("Official curriculum request failed.") from error
    if len(raw) > max_bytes:
        raise CurriculumFetchError("Official curriculum response exceeds the size limit.")
    if not raw:
        raise CurriculumFetchError("Official curriculum response is empty.")
    return raw, final_url