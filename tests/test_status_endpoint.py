import unittest
import asyncio
from app.routers.status import get_system_status

class TestStatusEndpoint(unittest.TestCase):
    def test_get_system_status_success(self):
        data = asyncio.run(get_system_status())

        self.assertIn("status", data)
        self.assertIn(data["status"], ["operational", "degraded"])
        self.assertIn("version", data)
        self.assertIn("timestamp", data)
        self.assertIn("services", data)

        services = data["services"]
        # Database check
        self.assertIn("database", services)
        self.assertIn("status", services["database"])
        self.assertEqual(services["database"]["status"], "operational")

        # Scanners check
        self.assertIn("scanners", services)
        scanners = services["scanners"]
        self.assertIn("secret_scanner", scanners)
        self.assertEqual(scanners["secret_scanner"]["status"], "operational")
        self.assertIn("bandit", scanners)
        self.assertIn("semgrep", scanners)

        # Worker queue check
        self.assertIn("worker_queue", services)
        self.assertIn("status", services["worker_queue"])

        # Auto-fix engine check
        self.assertIn("autofix", services)

if __name__ == "__main__":
    unittest.main()
