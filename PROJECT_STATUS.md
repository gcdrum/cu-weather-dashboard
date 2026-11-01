# CU Weather Dashboard — Project Status

Updated: 2026-10-31 (America/Chicago)

## Source of truth
Repository: gcdrum/cu-weather-dashboard. Read current repository files before modifying; do not rely on prior chat attachments. Main dashboard: index.html. Workflow: .github/workflows/main.yml.

## Confirmed
- GitHub connector read access works; repository has recent commits for RRFS live data, cycle/completion indicators, and responsive comparison charts.
- Workflow schedule: minutes 7,17,27,37,47,57 UTC, with workflow_dispatch; permissions contents: write.
- Workflow runs scripts/update_hrrr.py and scripts/update_rrfs.py; RRFS step is non-blocking.
- At inspection, rrfs_status.json: cycle 2026-11-01T00:00Z, 6/84 hours (7.1%), status partial, no errors.
- At inspection, hrrr_status.json: cycle 2026-11-01T01:00Z, 11/19 hours (57.9%), incomplete, newer 02Z retrieval returned 404.
- These status files do NOT establish whether subsequent workflow runs succeeded.

## Forecast design requirements
- Include HRRR, GFS, NAM where available, and RRFS. RRFS is not AI-supplemented.
- Separate nonconvective gradient-wind gusts from thunderstorm-driven convective gust risk. Use reflectivity to inform convective risk; avoid double counting.
- Threat outlook thresholds: Possible 30–39 mph; Possible Elevated 40–49; Likely 50–59; Extreme >=60 mph.
- Outage stages prioritize feeder count: stage 1 <=10; stage 2 10–30; stage 3 30–50; stage 4 50–80; stage 5 >=80 feeders. Historical calibration points: 40 mph ~5 feeders; 55 mph ~15; 60 mph ~20 for nonconvective winds.
- Display cycle (Z) and percent complete; keep model data updating without overwriting unrelated wind traces.

## Next checks
1. Verify GitHub Actions latest run status, timing, and logs; schedule declaration alone does not guarantee execution.
2. Confirm RRFS cycle and forecast-hour progress in published JSON; verify browser charts consume it correctly.
3. Investigate HRRR 404 cycle availability and avoid treating an unavailable new cycle as a failure of older valid data.
4. Validate live dashboard and forecasting risk logic before changing production.

## Working method
Use small commits and read the latest files directly from GitHub. Update this file after meaningful changes. Do not claim successful execution until runs/data confirm it.
