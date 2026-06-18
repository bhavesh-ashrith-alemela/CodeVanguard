import urllib.request
import urllib.parse
import http.cookiejar
import sys
import os
import time

# Create a cookie jar to automatically handle and store cookies across redirects
cookie_jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
urllib.request.install_opener(opener)

def test_security_features():
    print("=== STARTING SECURITY CONTROLS TEST ===")
    
    base_url = "http://127.0.0.1:8000"
    
    # 1. Verify Secure Headers are present on home page
    try:
        response = urllib.request.urlopen(base_url)
        headers = response.info()
        print("Verifying Secure Headers:")
        print(f"  X-Frame-Options: {headers.get('X-Frame-Options')}")
        print(f"  X-Content-Type-Options: {headers.get('X-Content-Type-Options')}")
        print(f"  Content-Security-Policy: {headers.get('Content-Security-Policy')[:45]}...")
        
        assert headers.get('X-Frame-Options') == "DENY", "X-Frame-Options header missing or incorrect"
        assert headers.get('X-Content-Type-Options') == "nosniff", "X-Content-Type-Options header missing or incorrect"
        assert "default-src 'self'" in headers.get('Content-Security-Policy'), "CSP missing default-src directive"
        print("  [PASS] Secure Headers verify successfully.")
    except Exception as e:
        print(f"FAILED secure headers test: {e}")
        sys.exit(1)

    # 2. Access Control: Request Admin Dashboard without Session Cookie
    try:
        req = urllib.request.Request(f"{base_url}/admin/dashboard")
        # Python's urlopen automatically follows redirects. 
        # The final URL after redirecting unauthorized access should be the login page.
        resp = urllib.request.urlopen(req)
        final_url = resp.geturl()
        print(f"Admin Dashboard Redirect URL (no cookie): {final_url}")
        assert "/admin/login" in final_url, "Unauthorized access did not redirect to login page!"
        print("  [PASS] Unauthorized dashboard access redirected successfully.")
    except Exception as e:
        print(f"FAILED auth dashboard access test: {e}")
        sys.exit(1)

    # 3. Access Control: Scan deletion without Session Cookie (Should return 401/403)
    try:
        req = urllib.request.Request(f"{base_url}/scans/some_mock_id", method="DELETE")
        try:
            urllib.request.urlopen(req)
            print("FAILED: Allowed scan delete without authentication!")
            sys.exit(1)
        except urllib.error.HTTPError as he:
            print(f"Unauthorized Delete Scan status code: {he.code}")
            assert he.code in (401, 403), f"Unexpected status code for unauth delete: {he.code}"
            print("  [PASS] Unauthorized scan deletion rejected successfully.")
    except Exception as e:
        print(f"FAILED unauth delete test: {e}")
        sys.exit(1)

    # 4. Admin Authentication & Session management
    try:
        post_data = urllib.parse.urlencode({
            "username": "admin",
            "password": "VanguardAdmin2026!"
        }).encode("utf-8")
        
        req = urllib.request.Request(f"{base_url}/admin/login", data=post_data, method="POST")
        resp = urllib.request.urlopen(req)
        
        # Verify cookie is in the jar
        cookies = list(cookie_jar)
        print(f"Cookie Jar contents: {cookies}")
        assert len(cookies) > 0, "Login did not set any cookies in the jar!"
        
        session_cookie = cookies[0]
        assert session_cookie.name == "session_token", "Session cookie name incorrect"
        
        print("  [PASS] Successfully logged in and session cookie is stored in cookie jar.")
    except Exception as e:
        print(f"FAILED admin login test: {e}")
        sys.exit(1)

    # 5. Access Control: Request Admin Dashboard with Session Cookie
    try:
        req = urllib.request.Request(f"{base_url}/admin/dashboard")
        # Cookie is sent automatically by installed HTTPCookieProcessor opener
        resp = urllib.request.urlopen(req)
        html = resp.read().decode("utf-8")
        assert "Admin Command Center" in html, "Dashboard did not render when authenticated"
        assert "Logged in as" in html, "Dashboard missing admin details"
        print("  [PASS] Dashboard accessible with valid session cookie.")
    except Exception as e:
        print(f"FAILED auth session dashboard test: {e}")
        sys.exit(1)

    # 6. Rate Limiting: Login brute force protection (Trigger rate limit blocker)
    print("Testing Login Rate Limiter (brute-force check):")
    rate_limited = False
    for i in range(10):
        try:
            post_data = urllib.parse.urlencode({
                "username": "admin",
                "password": "wrong_password_attempt"
            }).encode("utf-8")
            req = urllib.request.Request(f"{base_url}/admin/login", data=post_data, method="POST")
            resp = urllib.request.urlopen(req)
        except urllib.error.HTTPError as he:
            if he.code == 429:
                print(f"  Triggered rate limiting (429 Too Many Requests) at attempt #{i+1}")
                rate_limited = True
                break
            elif he.code in (401, 403):
                # Standard credentials error, continue trying to trigger rate limit
                pass
        time.sleep(0.1)
        
    assert rate_limited, "Rate limiter did not block logins after multiple failed attempts!"
    print("  [PASS] Login rate limiter triggered successfully.")
    
    print("=== ALL SECURITY CONTROLS TESTED SUCCESSFULLY ===")

if __name__ == "__main__":
    test_security_features()
