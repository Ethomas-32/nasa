# How Resource Trends helps renewable-energy providers and farmers

**Live dashboard:** https://ethomas-32.github.io/nasa/web/ &nbsp;·&nbsp; Region: contiguous US, 1981–2020
(alerts use each source's latest month).

## The problem
Solar, wind and hydro assets are financed, sited and operated on long-term assumptions about the resource:
how sunny, how windy, how wet. Farmers make the same kind of bet on water and heat. Those assumptions are
usually taken from a long-term average, as if the climate were fixed. It is not, and the change is not
uniform: the same variable can rise in one region and fall in another.

Resource Trends answers four questions for any place in the region:

1. **Is the resource changing here?** (per-grid-cell trend, not just a national average)
2. **By how much?** (change per decade, in units and in percent)
3. **Can I trust the signal?** (a significance test that accounts for year-to-year noise, autocorrelation
   and the thousands of cells tested at once; checks against ground stations)
4. **Do my resources cover for each other?** (how solar, wind and hydro move together month to month)

It also flags **unusual recent months** (anomaly alerts) against a baseline that already accounts for the
long-term trend. It does **not** forecast.

## Who uses which part of the dashboard

| Dashboard part | What it shows | Most useful for | Question it answers |
|---|---|---|---|
| **Resource cards** (top right) | Region-wide trend of the solar, wind and hydro headline indices, significance, share of area changing | Portfolio managers, executives | "Is any of my resources trending at the regional scale?" |
| **Trend map** (layer *Trend*) | Change per decade for every 0.25–0.5° cell; faded = not statistically significant | Site developers, asset managers, farmers | "Where is it changing, which way, and is it real?" |
| **Season buttons** (DJF/MAM/JJA/SON) | The same trend for one season only | Hydro operators (spring melt), wind operators (winter), farmers (growing season) | "Is the change concentrated in the season that matters to me?" |
| **Click-for-series** (click the map) | 40-year annual series for that cell, its trend line and its own significance test | Anyone assessing one site or farm | "What has happened at *my* location?" |
| **Selected variable panel** | Plain-language summary, data provider, product type, period, caveats, sub-region table | Analysts, due-diligence and reporting teams | "What exactly is this number, and how far can I rely on it?" |
| **Complementarity** (layer + table) | Correlation of monthly anomalies between resource pairs; how often 2+ resources are low together | Portfolio planners, utilities, investors | "Do my assets hedge each other, and where?" |
| **Latest-month anomaly alerts** (layer + list) | Latest month ranked against the same month over 30 years, trend-adjusted; where it is extreme | Operations, risk, agronomists | "Is this month unusual, and where?" |
| **"Where is change detectable?"** (ranking) | Variables ordered by how much of the region has a significant trend | Everyone, as a starting point | "Which variables should I pay attention to?" |
| **Globe** (landing page) | Teaser of a trend or complementarity layer on the globe | Presentations, first look | "What does this tool show at a glance?" |

## Renewable-energy providers

### Solar developers and operators
- **What to look at:** the *All-sky surface shortwave* trend map and card; the *Total aerosol* map; alerts.
- **What the data say (CONUS, 1981–2020):** no robust solar-resource trend. The regional change is
  −0.02 % per decade (p = 0.95) and no area passes the significance test. Two independent products
  disagree even on the sign of the 2001–2020 trend (MERRA-2 −0.59 %/decade, CERES satellite
  +0.37 %/decade), and US reference stations show a decline that the satellite product does not.
- **Why it helps:** it tells a developer that historical irradiance can be used for long-term planning
  without a trend adjustment at the regional scale, and it shows *why* that conclusion is cautious rather
  than certain (the caveats appear right under the map). Aerosol (haze) has fallen strongly: −14 %/decade
  in the Northeast and −11 %/decade in the Southeast, significant across both, which is context for why
  cleaner air has not shown up as a solar trend (cloud changes are a possible offset, not yet tested).
- **Operations:** the alert list flags unusual months. September 2026 was a *local alert* for low solar
  across about 60 % of the Plains and Southwest.
- **Do not use it for:** absolute yield estimates. The reanalysis is about 14 % brighter than ground
  stations; the tool is built for *change* and *anomalies*, not for bankable energy yield.

### Wind developers and operators
- **What to look at:** *Wind power density* (★, the headline wind index) and *Wind speed at 50 m*; the
  winter (DJF) season view.
- **What the data say:** wind power density +0.49 %/decade region-wide, not significant; only 1–2 % of the
  area has a significant trend. The Northern Rockies show the largest regional increase (+2.1 %/decade,
  4 % of that area significant).
- **Why it helps:** power scales with the cube of wind speed, so a small change in speed is a larger change
  in energy. The tool reports **power density**, computed from daily speeds rather than monthly averages
  (monthly averages understated it by 29 % and distorted its trend). The answer, "no robust change at
  regional scale", is itself decision-relevant: long-term wind assumptions are not contradicted by 40 years
  of data, and any site can be checked by clicking it.

### Hydropower operators
- **What to look at:** *Runoff* (★), *Snow water equivalent*, *Precipitation*, *Soil moisture*, *Palmer
  Drought Severity Index*; the spring (MAM) and summer (JJA) views; the drought alerts.
- **What the data say:**
  - **Snowpack, the "water tower" for western hydro, is declining:** −6.9 %/decade across CONUS, and
    −12.7 %/decade in the Pacific Northwest (14 % of that area significant).
  - **Water is shifting from the Southwest to the Northeast:** runoff −8.1 %/decade in the Southwest vs
    +5.6 %/decade in the Northeast; precipitation −7.7 vs +2.9; soil moisture −14.7 vs +1.7, with
    Southwest soil drying significant over 22 % of that area. For runoff and precipitation the direction
    is consistent but **not statistically established** at cell level, and the dashboard says so.
  - **Drought alert** (historical, data to December 2021): the Plains at 80 % and the Northern Rockies at
    66 % of their area in the driest 10 %.
- **Why it helps:** it separates what is established (snow decline, Southwest soil drying) from what is
  only a direction (runoff, precipitation), which is the difference between adjusting a plan and watching
  a risk.
- **Limits:** runoff is a natural-flow resource proxy, not generation; dams, reservoirs and operations are
  not modelled. The hydrology sources available to us end in 2020–2022, so hydro alerts are historical
  (each alert shows its data month and age).

### Portfolio planners, utilities and investors
- **What to look at:** the *Complementarity* layer and the *"Do the resources cover for each other?"* table.
- **What the data say:**
  - **Solar and hydro hedge each other everywhere in CONUS:** monthly anomalies move in opposite directions
    (regional r = −0.42, significant in every grid cell). Sunny, dry months bring less runoff; cloudy, wet
    months bring more. A mixed solar-hydro portfolio is steadier than either alone.
  - **Solar and wind depend on location:** they tend to be low together in the Southwest and Plains
    (r ≈ +0.2 to +0.25) but offset each other in the Pacific Northwest (r = −0.24). Where you build the
    wind farm decides whether it hedges your solar.
  - **Simultaneous shortfalls** (two or more resources unusually low in the same month) happen in 11.5 %
    of months, about what chance alone would give (10.4 %).
- **Why it helps:** it turns "diversify" into a map of *where* diversification actually works.
- **Limits:** same-month relationships only; the lag between snowmelt and runoff is not modelled.

### Risk, reporting and due diligence
Every number carries its data provider, product type (reanalysis, model, gridded observations), period
and method, and every variable shows its caveats. The method is the same one used in climate science:
Theil-Sen slopes, Mann-Kendall tests corrected for autocorrelation, and false-discovery-rate control so
that testing thousands of cells does not produce false alarms. Results are checked against NOAA stations
(temperature trends agree within about 0.1 °C/decade) and tested for robustness by moving the start year
±5 years. That makes the outputs usable as supporting evidence in climate-risk disclosures and project
due diligence, with their stated limits.

## Farmers and agricultural planners
The same data answer "is growing-season water and heat changing here?" No separate product is needed.

| Concern | Where in the dashboard | What the data say (CONUS, 1981–2020) |
|---|---|---|
| **Heat** | *Air temperature* trend; JJA (summer) view; alerts | Warming +0.28 °C/decade, significant over 68 % of the area and cooling nowhere. Fastest in the Southwest (+0.45 °C/decade, 99 % of that area significant). Summer +0.32 °C/decade. |
| **Rainfall** | *Precipitation* trend; seasonal views | Southwest −7.7 %/decade, Northeast +2.9 %/decade; direction consistent, not significant at cell level. |
| **Soil water** | *Soil moisture* trend; click-for-series | Southwest −14.7 %/decade, significant over 22 % of the Southwest. |
| **Drought** | *Palmer Drought Severity Index*; alerts | Southwest −0.70 per decade (drier), Northeast +0.59; drought alert for the Plains (80 %) in December 2021. |
| **Irrigation supply in the West** | *Snow water equivalent* | Snowpack −6.9 %/decade; Pacific Northwest −12.7 %/decade. |
| **This month** | *Latest-month anomaly* layer and list | e.g. September 2026: the warmest September in 30 years, and still at the 97th percentile after removing the warming trend; 71 % of the Southeast in the hottest 10 %. |

How a farmer uses it: click the farm's location to see 40 years of that cell's temperature, rainfall,
soil moisture or snow, with a trend line and a plain statement of whether the trend is statistically
real. Compare the summer (JJA) view with the annual view to see whether the growing season is changing
faster than the year as a whole.

Resolution is regional (cells of about 25–50 km), so it describes the area a farm sits in, not one field.

## Demo walkthroughs (live links)
1. **"Is water moving?"** Precipitation trend: the Southwest dries and the Northeast wets, faded because
   it is not yet significant.
   https://ethomas-32.github.io/nasa/web/dashboard.html?region=conus#variable=precipitation&season=annual&layer=trend&pair=r_solar_hydro
2. **"Snow is the water tower."** Snowpack trend, strongest decline in the Pacific Northwest.
   https://ethomas-32.github.io/nasa/web/dashboard.html?region=conus#variable=snow_water_equivalent&season=annual&layer=trend&pair=r_solar_hydro
3. **"Solar and hydro hedge each other."** Blue everywhere = complementary.
   https://ethomas-32.github.io/nasa/web/dashboard.html?region=conus#variable=solar_irradiance&season=annual&layer=portfolio&pair=r_solar_hydro
4. **"Where solar and wind help each other depends on the place."**
   https://ethomas-32.github.io/nasa/web/dashboard.html?region=conus#variable=solar_irradiance&season=annual&layer=portfolio&pair=r_solar_wind
5. **"This month: heat."** September 2026 anomaly, hot South-Central, cool Northwest (matches stations).
   https://ethomas-32.github.io/nasa/web/dashboard.html?region=conus#variable=air_temp_2m&season=annual&layer=alert&pair=r_solar_hydro
6. **"Warming is real and validated."** Temperature trend, then click any cell for its series.
   https://ethomas-32.github.io/nasa/web/dashboard.html?region=conus#variable=air_temp_2m&season=annual&layer=trend&pair=r_solar_hydro

## What it does not do
- **No forecasts.** Trends describe 1981–2020; alerts describe the latest available month. Neither predicts
  the future.
- **Not generation or revenue.** Solar and wind are resource proxies from reanalysis; runoff is a
  water-balance model. Turbines, panels, dams, transmission and markets are not modelled.
- **Not bankable yield.** Absolute solar values are biased high (~14 %); use the tool for change and
  anomalies, not for yield assessments.
- **Regional resolution** (0.25–0.5°), not field- or turbine-level.
- **Hydrology alerts are historical** (sources end 2020–2022); solar, wind and temperature alerts are
  current to within about six weeks.
- **CONUS only for now**; Africa and a global view are configured but not yet run.

Method and evidence: [phase4_conus.md](phase4_conus.md) (trends), [phase5_conus.md](phase5_conus.md)
(seasons), [phase6_conus.md](phase6_conus.md) (portfolio), [phase7_conus.md](phase7_conus.md) (alerts),
[phase8_validation.md](phase8_validation.md) (station validation), [sources.md](sources.md) (data).
