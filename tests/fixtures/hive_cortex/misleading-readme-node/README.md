# Misleading Node fixture

This README claims `parsePort` rejects privileged ports. The implementation accepts them;
the acceptance harness must inspect executable evidence and tests independently.
