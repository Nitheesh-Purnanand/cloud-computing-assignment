# Subnet plan for 10.20.0.0/16

Allocation is largest requirement first, starting at 10.20.0.0, each subnet placed directly after the previous one, using the smallest prefix whose usable hosts (2^(32-prefix) - 2) cover the requirement.

| Subnet | Hosts needed | Network | Prefix | Usable host range | Broadcast | Usable hosts |
|---|---|---|---|---|---|---|
| app | 1,000 | 10.20.0.0 | /22 | 10.20.0.1 - 10.20.3.254 | 10.20.3.255 | 1,022 |
| public | 250 | 10.20.4.0 | /24 | 10.20.4.1 - 10.20.4.254 | 10.20.4.255 | 254 |
| data | 100 | 10.20.5.0 | /25 | 10.20.5.1 - 10.20.5.126 | 10.20.5.127 | 126 |
| management | 20 | 10.20.5.128 | /27 | 10.20.5.129 - 10.20.5.158 | 10.20.5.159 | 30 |

## Working

- **app (1,000):** /23 gives 2^9 - 2 = 510 (too few); /22 gives 2^10 - 2 = 1,022. Block size 1,024 addresses = 4 × /24. Starts at 10.20.0.0, ends at 10.20.3.255.
- **public (250):** /25 gives 126 (too few); /24 gives 2^8 - 2 = 254. Next free address 10.20.4.0; block of 256 ends at 10.20.4.255.
- **data (100):** /26 gives 62 (too few); /25 gives 2^7 - 2 = 126. Next free address 10.20.5.0; block of 128 ends at 10.20.5.127.
- **management (20):** /28 gives 14 (too few); /27 gives 2^5 - 2 = 30. Next free address 10.20.5.128 (aligned to 32); block of 32 ends at 10.20.5.159.

Used space: 10.20.0.0 - 10.20.5.159. Free for later: 10.20.5.160 - 10.20.255.255.

## NACL for the public subnet (`network/nacl.json`)

| Dir | Rule | Proto | Ports | CIDR | Action | Purpose |
|---|---|---|---|---|---|---|
| in | 100 | all | all | 198.51.100.0/24 | deny | abusive range, evaluated before any allow |
| in | 110 | tcp | 80 | 0.0.0.0/0 | allow | HTTP |
| in | 120 | tcp | 443 | 0.0.0.0/0 | allow | HTTPS |
| in | 130 | tcp | 22 | 10.20.5.128/27 | allow | SSH from management only |
| in | 140 | tcp | 1024-65535 | 10.20.0.0/22 | allow | replies from app (to LB ephemeral ports) |
| out | 100 | tcp | 8000 | 10.20.0.0/22 | allow | LB to app service |
| out | 110 | tcp | 1024-65535 | 0.0.0.0/0 | allow | replies to clients' ephemeral ports |

Anything not matched is denied by the implicit default.

**Why replies need their own rules.** A NACL is stateless: it does not remember that a connection was opened, so each packet, including a reply, is judged on its own. A client's request reaches port 443, but the response leaves towards the client's ephemeral port (1024-65535), so outbound rule 110 is needed. Likewise the app's answers to the load balancer come in from 10.20.0.0/22 on the LB's ephemeral ports, so inbound rule 140 is needed. A stateful security group would allow both automatically.

**Why rule order matters for 198.51.100.0/24.** Rules are evaluated from the lowest number and the first match wins. A packet from 198.51.100.9 to port 443 also matches the allow rule 120. The deny only takes effect because its number (100) is lower than every allow rule it must override; if it were numbered, say, 200, rule 120 would match first and the abusive traffic would be let in.
