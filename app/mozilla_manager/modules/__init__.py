"""Domain modules — each functional area is isolated for maintenance.

| module         | responsibility                              |
|----------------|---------------------------------------------|
| system         | boot / health / root layout / gc / sandbox  |
| profiles       | env CRUD, launch/stop, check, export        |
| groups         | group aggregation                           |
| proxies        | proxy inventory from profiles               |
| subscriptions  | sub import + refresh + node list            |
| mihomo_svc     | local mihomo process control                |
| doctor_svc     | environment self-check                      |
| templates      | country packs / fingerprints / bind-node    |
| sessions       | session backup / restore                    |
| nodes_svc      | favorites / latency / country groups        |
| health         | egress check / rebind / IP recommend        |
| extensions     | runtime/extensions + profile enable list    |
"""
