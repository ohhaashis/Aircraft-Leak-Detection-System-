# 1. Problem Statement and Objectives

## The problem

Aircraft hydraulic systems move flight-control surfaces, landing gear and brakes using high-pressure
fluid. A leak — from a worn seal, a cracked fitting or a fatigued pipe — wastes fluid, lowers system
pressure and, if undetected, can disable an actuation system.

Today, aircraft monitor system-level parameters such as reservoir quantity and pressure. These reveal
*that* something is wrong, but not *where*. Technicians then search manually, which is slow in
dense, hard-to-reach hydraulic bays.

## Our goal

Build a **low-cost, laboratory-scale leak detection system** that monitors a miniature hydraulic loop
and, in real time:

1. **Detects** abnormal leakage,
2. **Quantifies** the leak rate,
3. **Localises** the leak to a specific zone of the pipe network,
4. **Discriminates** true leaks from normal operating changes (pump speed changes, valve movements,
   knocks on the pipe),
5. **Alerts and logs** each event on a live monitoring dashboard.

It is a maintenance-assistance demonstrator for a design practicum, **not** an aircraft-certified system.

## Project objectives (from the project sheet)

| # | Objective | How we meet it |
|---|---|---|
| 1 | Zone-based sensor setup for pressure and flow differential sensing | 2 pressure + 2 flow sensors at loop inlet and outlet; 4 PZT discs, one per steel segment |
| 2 | Detection and quantification of leakage from pressure and flow deviations | Mass balance (Q1 − Q2) + ML leak-rate regressor trained on measured leak volumes |
| 3 | Localisation to a zone; discrimination from normal changes | 4-class ML classifier (no leak / L1 / L2 / L3) trained with "normal but disturbed" runs; alarm persistence filter |
| 4 | Definition of sensing parameters: sensors, sampling, accuracy, response time, minimum detectable leak | See [03_hardware_and_circuits.md](03_hardware_and_circuits.md) and [05_machine_learning.md](05_machine_learning.md) (3σ minimum detectable leak) |
| 5 | Real-time alerting and logging; bench testing with ISO VG32 oil | Streamlit dashboard with event log; ~70 labelled runs in VG32 oil |

## Test conditions

| Parameter | Value |
|---|---|
| Fluid | ISO VG32 hydraulic oil (debugging with water first) |
| Pipe | 12 mm OD mild steel, 1 mm wall |
| Network | Rectangular loop, about 5 ft × 4 ft |
| Pump | 12 V, 60 W diaphragm pump, up to 5 L/min (water), speed set by PWM controller |
| Leaks | L1: centre T ball valve (adjustable); L2, L3: 2–3 mm drilled holes sealed by rubber + hose clamp |

## Team (Group 32, IIT Mandi, Design Practicum IC-202P22)

| Member | Branch |
|---|---|
| Ashish Kumar | DSAI |
| Nishant Thamman | ME |
| Aman Kumar | CSE |
| Badavath Thirumalesh | EE |
| Bhoomika | GE |
| Ananya Sharma | MSE |
