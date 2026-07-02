from urllib.parse import urlparse
from fastapi import Request, HTTPException

def verify_csrf(request: Request):
    """
    Validates the Origin and Referer headers against the Host header
    to protect endpoints from Cross-Site Request Forgery (CSRF).
    """
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    host = request.headers.get("host")
    
    if origin:
        parsed_origin = urlparse(origin)
        if parsed_origin.netloc != host:
            raise HTTPException(status_code=403, detail="CSRF check failed: Origin mismatch.")
    elif referer:
        parsed_referer = urlparse(referer)
        if parsed_referer.netloc != host:
            raise HTTPException(status_code=403, detail="CSRF check failed: Referer mismatch.")
    else:
        raise HTTPException(status_code=403, detail="CSRF check failed: Missing Origin or Referer header.")
