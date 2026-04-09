# IAM Resiliency Demo - Presenter Notes

**Demo Version:** 1.0  
**Target Audience:** Ory, Teleport, and technical decision-makers  
**Duration:** 15-20 minutes (flexible)  
**Last Updated:** 2026-04-09

---

## 🎯 Core Message

**"Identity and Access Management systems need to be always available. CockroachDB makes that possible by surviving complete region failures without manual intervention."**

---

## 📋 Pre-Demo Checklist

### Before the Presentation

- [ ] All three regional apps are running and connected
- [ ] Backups on the CRDB Cluster are off
- [ ] Maintenance Window on the CRDB Cluster are set to not interfere with the demo
- [ ] Grafana is accessible at `http://<primary-ip>:3000`
- [ ] All dashboards are displaying metrics (check last 5 minutes)
- [ ] Terminal windows arranged for screen sharing:
  - Window 1: Region 1 app output
  - Window 2: Region 2 app output  
  - Window 3: Region 3 app output
  - Window 4: Disruption commands (`disrupt.sh`)
- [ ] Browser tabs open:
  - Grafana dashboard (decide which one to use)
  - CockroachDB Cloud Console (cluster overview)
- [ ] Test disruption/recovery cycle (run 1 hour before if possible)
- [ ] Have `demo-env.sh` sourced in disruption terminal
- [ ] Know your cluster regions by heart (avoid fumbling)
- [ ] Demo Slides `https://docs.google.com/presentation/d/1JCN_tjBfSOfS37ht0zshIOGdsOfJZRPHdlk_ybJM8yo/edit?slide=id.g2b6c6946b7e_0_2297#slide=id.g2b6c6946b7e_0_2297` are ready to go

### Environment Variables to Verify

```bash
source demo-env.sh
echo $CRDB_CLUSTER_ID    # Should show cluster UUID
echo $DATABASE_REGIONS   # Should show your 3 regions
./disrupt.sh list        # Should return cluster nodes
```

---

## 🎬 Suggested Presentation Flow

### Act 1: Setup & Context (3-5 minutes)

**What to Show:**
- Terminal windows with apps running
- Grafana dashboard showing normal operations

**What to Say:**

>"Let's start with a brief deck that explains a couple of concepts and provides an overview of the architecture used in the demo
>
> Let me show you what happens when an entire region goes down in a production IAM system.
> 
> We have a CockroachDB cluster deployed across three AWS regions: [name your regions]. Each region is running an identical IAM application that handles user authentication, sessions, audit logging.
> 
> [Point to Grafana] Here you can see real-time metrics from all three regions. Notice the latency patterns:
> 
> - **Global tables** (users, roles) - Fast reads everywhere (~X ms), slower writes (~Y ms) because they need consensus across regions
> - **Regional tables** (sessions) - Very fast in the primary region (~Z ms) 
> - **Regional-by-row tables** (audit logs) - Fast writes (~A ms) because each row lives in its designated region
> 
> [Point to terminal] Each app is processing continuous authentication flows: login, permission checks, audit logging, logout - simulating a real production IAM system."

**Key Talking Points:**
- Emphasize this is a **real distributed database**, not a simulation
- Each app only connects to the database - no app-to-app communication
- CockroachDB handles all the replication and routing automatically
- This demonstrates **resiliency**, not IAM complexity or performance.   

---

### Act 2: Demonstrate Normal Operations (2-3 minutes)

**What to Show:**
- Console output from all three regions showing healthy stats
- Grafana showing consistent latencies
- Optional: Anomaly detection catching suspicious logins

**What to Say:**

> "All three applications are operating independently. Each one:
> 
> 1. Authenticates users (creates sessions)
> 2. Checks permissions (reads global user/role data)
> 3. Logs all actions to audit trails
> 4. [If anomaly detection is running] Uses vector similarity search to detect unusual login patterns
> 
> [Point to specific metrics] Notice these latencies are stable. The database is serving requests from local replicas, giving us single-digit millisecond reads."

**Optional Deep Dive:**
- Show one complete user session cycle in the code
- Explain AOST (As Of System Time) follower reads if asked
- Discuss the three table locality types if audience is technical

---

### Act 3: The Disruption (5-7 minutes)

**What to Show:**
- Run `./disrupt.sh region [region-name]`
- Watch failed region's app enter reconnection loop
- Watch Grafana show the failure
- Show DB Console marking nodes as "Suspect" then "Dead"

**What to Say:**

> "Now let's simulate a complete region failure - this could be a cloud provider outage, network partition, or datacenter issue.
> 
> [Run disruption command]
> 
> ```bash
> ./disrupt.sh region aws-us-east-2
> ```
> 
> [Wait for effect, point to screens]
> 
> Watch what happens:
> 
> 1. [Point to disrupted region terminal] **Region 2's app** immediately detects the connection loss and enters a retry loop. It's NOT failing over to another region - it's waiting for its region to recover.
> 
> 2. [Point to other terminals] **Regions 1 and 3** continue operating normally. Users in those regions experience ZERO downtime.
> 
> 3. [Point to Grafana] The metrics clearly show Region 2 is down - its graphs flatline, status turns red.
> 
> 4. [Point to DB Console] CockroachDB marks the nodes as 'Suspect' and after about 75 seconds, marks them as 'Dead'. The cluster automatically adjusts - remaining nodes pick up leaseholder responsibilities.
> 
> This is the key insight: **The IAM system remains available**. Two-thirds of your users are completely unaffected. The third are in a graceful retry state, not seeing errors or corrupted data."

**Critical Timing:**
- **0-5 seconds:** App detects connection loss (thanks to aggressive TCP timeouts)
- **~5-10 seconds:** Grafana shows flatline metrics
- **~75 seconds:** DB Console marks nodes as "Dead"
- **Ongoing:** Surviving regions continue serving requests

**Common Questions During This Phase:**
- Q: "What about users in the failed region?"  
  A: "They're in a retry loop. When the region recovers, they automatically reconnect. No data loss, no manual intervention needed."

- Q: "Can you route Region 2 users to Region 1?"  
  A: "Absolutely - that's a load balancer configuration. We're showing regional isolation here to demonstrate the database's resilience. In production, you'd typically have multi-region load balancing."

- Q: "How long can it stay down?"  
  A: "Indefinitely. The other regions operate normally. The only limit is your business tolerance for regional unavailability."

---

### Act 4: The Recovery (3-5 minutes)

**What to Show:**
- Run `./disrupt.sh clear`
- Watch failed region's app automatically reconnect
- Show Grafana metrics resume
- Point out latency may be briefly elevated during rebalancing

**What to Say:**

> "Now let's recover the region.
> 
> [Run recovery command]
> 
> ```bash
> ./disrupt.sh clear
> ```
> 
> [Point to disrupted region terminal]
> 
> Watch - within seconds, Region 2's app **automatically reconnects**. No operator intervention. No manual failback process. No configuration changes.
> 
> [Point to Grafana]
> 
> Metrics resume immediately. You might notice latencies are slightly elevated for the first minute - that's CockroachDB rebalancing leaseholders and bringing replicas up to date. This settles within 60-90 seconds.
> 
> [Point to all terminals]
> 
> All three regions are now operating normally again. The entire failure and recovery was handled automatically by the database."

**Key Talking Points:**
- Zero manual intervention required
- No data loss (show audit log continuity if time permits)
- Automatic rebalancing optimizes for performance
- This works the same way for real cloud provider outages

---

### Act 5: Wrap-Up & Technical Deep Dive (2-3 minutes)

**What to Say:**

> "So what did we just see?
> 
> 1. **True multi-region active-active** - All regions serving requests simultaneously
> 2. **Automatic failure detection** - Sub-second to seconds, depending on your timeout configuration
> 3. **Graceful degradation** - Failed region retries, healthy regions continue
> 4. **Zero-touch recovery** - Apps automatically reconnect when the region returns
> 5. **No data loss** - Strong consistency guarantees maintained throughout
> 
> For an IAM system, this means:
> - Your authentication service stays available during regional outages
> - Session state is preserved across failures
> - Audit logs are never lost
> - No complex failover orchestration needed
> 
> This is the foundation that lets you deliver the 99.999% availability SLA that identity systems require."

**If Time Permits - Technical Details:**
- Explain table locality types in more depth
- Show the schema (`schema.sql`)
- Discuss the anomaly detection vector similarity feature
- Walk through the retry logic in `helpers.py`
- Show Prometheus metrics endpoint

---

## ❓ Common Questions & Answers

### Database & Architecture

**Q: How does this compare to running separate databases per region?**  
A: With separate databases, you need to:
- Manage replication yourself
- Handle conflict resolution
- Build failover logic
- Risk split-brain scenarios
- Manually keep schemas in sync

CockroachDB handles all of this automatically with strong consistency guarantees.

**Q: What about write latency to global tables?**  
A: Global tables prioritize consistency and read performance. Writes require consensus (~XX ms in this demo). For write-heavy workloads, use Regional or Regional-by-Row tables. Most IAM operations are read-heavy.

**Q: Can you mix table locality types in one database?**  
A: Yes! That's exactly what we're doing. Choose the right locality for each table's access pattern:
- Users/Roles = Global (read-heavy, must be consistent everywhere)
- Sessions = Regional (write-heavy, region-specific)
- Audit Logs = Regional-by-Row (naturally partitioned by region)

**Q: How does CockroachDB know when a node is dead?**  
A: It uses a heartbeat mechanism. After ~9 seconds without heartbeats, nodes are marked "Suspect". After ~75 seconds total, they're marked "Dead" and the cluster rebalances. These timings are configurable.

**Q: What happens to in-flight transactions during a failure?**  
A: They fail and are retried. Notice in our `helpers.py` we have retry logic that handles serialization failures (40001) and unknown transaction states (40003). This is standard practice for distributed databases.

### Demo-Specific

**Q: Why don't the apps fail over to another region?**  
A: We're demonstrating database resiliency, not application failover. In production, you'd use multi-region load balancers (AWS ALB, GCP GLB, etc.) to route users to healthy regions. The point here is the *database* survives without reconfiguration.

**Q: Is this running on real cloud infrastructure?**  
A: Yes. CockroachDB Cloud Advanced cluster across real AWS regions. The apps are on EC2 instances. This is production-grade infrastructure.

**Q: Can you fail over multiple regions?**  
A: The cluster needs a quorum (majority) to operate. With 3 regions, you can lose 1. With 5 regions, you can lose 2. For production, we typically recommend at least 3 regions for fault tolerance.

**Q: What's the anomaly detection feature?**  
A: It uses vector embeddings to represent user login behavior (time of day, day of week, region). We calculate cosine similarity between current login and the user's profile. Distance above a threshold flags the login as anomalous. This demonstrates CockroachDB's vector similarity search capabilities for ML/AI workloads.

### Operational

**Q: How do you monitor this in production?**  
A: [Point to Grafana] We're using Prometheus + Grafana here. In production, you'd also use:
- CockroachDB's built-in DB Console
- Cloud provider monitoring
- APM tools (Datadog, New Relic, etc.)
- Custom business metrics

**Q: What about backup and disaster recovery?**  
A: CockroachDB has built-in:
- Point-in-time restore (PITR)
- Automated backups to cloud storage
- Change data capture (CDC) for event streaming
- This demo focuses on high availability; DR is a separate conversation

**Q: How much does this cost to run?**  
A: [Know your cluster size and rough costs] CockroachDB Cloud pricing is based on storage and compute. This demo cluster with [X nodes] across 3 regions costs approximately $Y/month. Production pricing scales with your workload.

**Q: Can this run in Kubernetes?**  
A: Yes. CockroachDB runs on:
- CockroachDB Cloud (fully managed - what we're using)
- Self-hosted on Kubernetes (using the operator)
- Self-hosted on VMs
- Hybrid (some regions cloud, some on-prem)

---

## 🚨 Troubleshooting Quick Fixes

### During the Demo

| Issue | Quick Fix | Prevention |
|-------|-----------|------------|
| App shows "Connection lost" before disruption | Check `./disrupt.sh list` - may have stale disruptions | Run `./disrupt.sh clear` before demo |
| Grafana dashboards not updating | Check Prometheus targets at `:9090/targets` | Verify `METRICS_PORT` matches Prometheus config |
| Disruption doesn't take effect | Verify API key permissions and cluster ID | Test disruption 1 hour before presentation |
| DB Console shows all nodes healthy after disruption | IP allowlist disruption takes 30-60s to propagate | Wait up to 90 seconds, mention this is expected |
| Recovery takes too long | Clear disruption, wait 2 minutes for IP allowlist to sync | Patience - explain propagation delay |
| "Permission denied" on `disrupt.sh` | `chmod +x disrupt.sh` | Check file permissions in setup |
| Terminal fonts too small for screen share | Increase terminal font size before demo | Test screen share resolution beforehand |

### Common Demo Gotchas

**Gotcha #1: IP allowlist propagation delay**
- When you run `disrupt.sh`, it can take 30-90 seconds for the IP allowlist changes to propagate through CockroachDB Cloud's infrastructure
- Fill this time by explaining what you're about to see
- Don't panic if nodes don't immediately show as dead

**Gotcha #2: Terminal window management**
- With 3+ terminal windows, it's easy to lose track
- Label each terminal clearly (e.g., `PS1="[REGION-1] $ "`)
- Use tmux/screen with named windows if comfortable

**Gotcha #3: Grafana dashboard selection**
- Different dashboards tell different stories
- **iam-demo-comparison.json** - Best for showing all regions overlaid
- **iam-demo-by-region.json** - Best for mimicking console output
- Choose ONE dashboard and stick with it

**Gotcha #4: Anomaly detection noise**
- If `ANOMALY_INJECTION_RATE` is too high, it becomes distracting
- Sweet spot: 5-10% for occasional interesting alerts
- Can disable entirely with `ENABLE_ANOMALY_DETECTION=false`

**Gotcha #5: Forgetting to source demo-env.sh**
- If `disrupt.sh` fails with "variable not set", you forgot to source
- Keep the source command visible in your disruption terminal

---

## 🎨 Presentation Tips

### Screen Sharing Setup

**Recommended Layout:**
```
+------------------+------------------+
|   Grafana        |   Terminal 1     |
|   Dashboard      |   (Region 1)     |
|                  |                  |
+------------------+------------------+
|   Terminal 2     |   Terminal 3     |
|   (Region 2)     |   (Region 3)     |
|                  |                  |
+------------------+------------------+
```

**Alternative: Terminal Focus**
```
+-----------------------------------+
|   Terminals (tiled, all 3)        |
|                                   |
+-----------------------------------+
|   Grafana (smaller, bottom)       |
+-----------------------------------+
```

### Pacing

- **Slow down** - Let people absorb what's happening
- **Narrate** - Don't assume people see what you see
- **Point** - Use cursor to highlight specific metrics
- **Pause** - After running disruption, give 10-15 seconds of silence to watch

### Engagement Techniques

- **Predict before showing:** "In about 5 seconds, you'll see Region 2's app enter a retry loop"
- **Ask rhetorical questions:** "What do you think happens to the other regions?" [pause] "Nothing. They keep running."
- **Use metaphors:** "Think of it like a traffic system - if one highway closes, the others handle the load while that highway is being repaired"
- **Quantify impact:** "In a real scenario, if 30% of your users are in this region, 70% experience zero downtime"

### Handling Technical Audiences

- Show the code: `demo.py`, `transactions.py`, `schema.sql`
- Explain retry logic and error codes (40001, 40003)
- Discuss CAP theorem and how CockroachDB is CP (consistency + partition tolerance)
- Dive into Raft consensus if asked
- Show Prometheus metrics raw format if they're interested

### Handling Executive Audiences

- Focus on business outcomes, not technical details
- Use phrases like "zero downtime", "automatic recovery", "no data loss"
- Relate to their pain points: "Have you ever had to wake someone up at 3 AM because a region failed?"
- Quantify: "This could reduce your operational overhead by X%"
- Keep it visual: "Red means down, green means up"

---

## 📊 Success Metrics for the Demo

After the presentation, you should have conveyed:

✅ **CockroachDB provides true multi-region active-active**  
✅ **Region failures are handled automatically without data loss**  
✅ **Recovery is automatic and requires no operator intervention**  
✅ **Different table locality types optimize for different access patterns**  
✅ **IAM systems can achieve 99.999% availability with this architecture**

---

## 🔖 Quick Reference Commands

```bash
# Start demo apps (after setup)
source demo-env.sh
./demo.py

# List cluster nodes and regions
./disrupt.sh list

# Disrupt a region
./disrupt.sh region aws-us-east-2

# Disrupt specific availability zones
./disrupt.sh az aws-us-west-2 a b

# Disrupt a single node
./disrupt.sh node cockroachdb-<node-id>

# Clear all disruptions
./disrupt.sh clear

# Check Grafana
http://<primary-ip>:3000
# Login: admin / admin

# Check Prometheus
http://<primary-ip>:9090

# Check app metrics endpoint
curl http://localhost:8000/metrics

# Restart app if needed
pkill -f demo.py
./demo.py

# Check app is running
ps aux | grep demo.py
```

---

## 📝 Post-Demo Follow-Up

### Materials to Share

- [ ] Link to this GitHub repository
- [ ] Architecture diagram (once created)
- [ ] Screenshots of Grafana dashboards during failure
- [ ] Recording of the demo (if permitted)
- [ ] CockroachDB documentation links:
  - [Multi-Region Overview](https://www.cockroachlabs.com/docs/stable/multiregion-overview.html)
  - [Table Localities](https://www.cockroachlabs.com/docs/stable/table-localities.html)
  - [Survive Region Failures](https://www.cockroachlabs.com/docs/stable/survive-failure.html)

### Next Steps to Suggest

1. **POC Planning:** Discuss their specific IAM requirements
2. **Architecture Review:** Review their current setup and migration path
3. **Sizing Exercise:** Calculate cluster size for their workload
4. **Technical Deep Dive:** Schedule time with CockroachDB solutions architects
5. **Trial Access:** Get them started with CockroachDB Cloud trial

---

## 🎯 Customization Notes

**For Ory (Identity Platform Company):**
- Emphasize session management and global user data
- Discuss OAuth2/OIDC token validation latency requirements
- Highlight audit log compliance needs (SOC2, GDPR)
- Focus on developer experience (schema changes, migrations)

**For Teleport (Privileged Access Management):**
- Emphasize security and compliance
- Discuss audit log immutability and query performance
- Highlight certificate/credential storage patterns
- Focus on zero-trust architecture compatibility
- Mention their likely need for low-latency session validation

**For Generic IAM Audiences:**
- Focus on availability SLAs
- Discuss cost of downtime for authentication
- Highlight operational simplicity vs. DIY solutions
- Compare to other database approaches (Aurora Global, Spanner)

---

## 📅 Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-04-09 | Initial presenter notes created |

---

**Remember:** You know this demo inside and out. Trust your expertise, stay calm during glitches, and focus on telling the resiliency story. The technology does the heavy lifting - your job is to make it relatable and compelling.

**Good luck! 🚀**
