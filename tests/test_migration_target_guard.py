"""Fail closed for non-CI, non-localhost and unexpected database targets."""
import unittest
from scripts.verify_postgres_migration_ci import validate_ephemeral_target

URL = "postgresql://ci_user:fictional-local-pass@127.0.0.1:5432/slickk_ci_test"
FLAGS = {"CI": "true", "SLICKK_EPHEMERAL_DB_TEST": "true"}

class MigrationTargetGuardTests(unittest.TestCase):
    def test_local_ephemeral_target_is_allowed(self):
        validate_ephemeral_target(URL, FLAGS)

    def test_missing_ci_opt_in_rejected(self):
        for flags in ({}, {"CI": "true"}, {"SLICKK_EPHEMERAL_DB_TEST": "true"}):
            with self.subTest(flags=flags), self.assertRaises(ValueError):
                validate_ephemeral_target(URL, flags)

    def test_remote_or_production_database_rejected(self):
        for target in ("postgresql://ci_user:pass@prod.example:5432/slickk_ci_test",
                       "postgresql://ci_user:pass@127.0.0.1:5432/slickk_ledger",
                       "postgresql://ci_user:pass@127.0.0.1:5433/slickk_ci_test",
                       "sqlite:///slickk_ci_test"):
            with self.subTest(target=target.rsplit("@",1)[-1]), self.assertRaises(ValueError):
                validate_ephemeral_target(target, FLAGS)

    def test_malformed_url_error_redacts_input(self):
        with self.assertRaisesRegex(ValueError, "Malformed") as ctx:
            validate_ephemeral_target("not a real url secret=fictional", FLAGS)
        self.assertNotIn("secret=fictional", str(ctx.exception))

if __name__ == "__main__":
    unittest.main()
