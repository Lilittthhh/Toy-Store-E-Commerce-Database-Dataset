# Session 3 Demonstration Checklist

1. Open Pipeline and show that every stage begins as **Not run**.
2. Open Contract; explain the RetailMetrics `.proto`, then run **Validate contract** and **Verify generated modules**.
3. Run Payload size; distinguish serialized bytes from network latency.
4. Run Unary latency; describe the measured local results without claiming a universal winner.
5. Run Round trips; confirm batch and individual calls return equal records and show the saved socket crossings.
6. Run Streaming; point first to time to first usable result, then separately discuss total completion time and sequence equality.
7. Run Adapter swap; show the unchanged caller, normalized equality, and measured transport values.
8. Run Deadline; show the short-timeout failure and successful generous-timeout retry.
9. Run Reconciliation; show exact Session 1/2 agreement and the refund comparison.
10. Open Console and the generated `results/` evidence. Show `database_safety.json` before/after equality and the loopback-only service addresses.
11. Close the GUI so its embedded service host stops cleanly.
