# Methods (load on demand)

Do not duplicate the loop in `SKILL.md`. Use these when the board is stuck or the next test is unclear.

## Gregg problem statement (answer all six before the first test)

1. What makes you think there is a problem?
2. Has this system ever performed well?
3. What changed recently (software, hardware, load, config)?
4. Can you express it as latency or runtime?
5. Does it affect others, or only this observer?
6. What is the environment (CPU, RAM, disk, network, versions)?

Unanswered questions are open hypotheses, not flavor text.

## Split-half (process of elimination)

Exonerate half the remaining set with one cheap test. Repeat.

- Ping the next hop: if it answers, the path _to_ that hop is out.
- Hit a sibling instance: if only one is sick, the shared dependency is out (or vice versa).
- Serve a static/health path: if that is fast, the listener and network are out.
- Compare a working request class with a failing one: whatever they share is in; whatever they don't is out.

A test that only confirms the favorite hypothesis is a wasted turn.

## GitLab drill-down (stop at the first layer that localizes)

1. Architecture — which box even owns this symptom?
2. Impact — who, how many, which error, since when?
3. What changed — deploys, config, certs, schema, flags, DNS, traffic.
4. Component — which process / container / task.
5. What requests share — path, tenant, shard, region, auth, payload shape.
6. Which dependency — DB, cache, queue, upstream, disk, DNS.
7. Trace — one request, hop by hop.
8. Contention — locks, saturations, queue depth, fds, mounts.
9. Profile — CPU/off-CPU only after the above have localized.

Do not profile a fleet to find a wrong target.

## USE (per resource) and RED (per service)

**USE** for each resource (CPU, mem, disk, net, fds, locks, queues, mounts):

- Utilization — busy fraction
- Saturation — wait queue / steal / full
- Errors — failed operations

A resource at high utilization with no saturation and no errors is working. Saturation or errors is the finding.

**RED** for each service:

- Rate — requests / events per second
- Errors — failed fraction
- Duration — latency distribution

Rate collapsed + errors up → dependency or crash. Rate held + duration up → saturation or slow dep. Errors up + duration flat → bad response, not hang.

## Time-division

Total observed latency = sum of synchronous parts. Write the budget:

```text
client →  edge →  app →  db →  app →  edge →  client
  ?ms     ?ms    ?ms    ?ms    ?ms    ?ms     = Tms
```

The largest unexplained slice is the next test. Do not start inside the app if the unexplained mass is DNS or TLS handshake.

Async work (queues, cron) is not in the sum until the request waits on it.

## Negative results

Publishing what you ruled out is progress (SRE Ch.12). Update the board. Do not re-run a test that already killed a hypothesis. Do not keep a killed hypothesis "in case."
