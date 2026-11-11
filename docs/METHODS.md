# Methods note

This note explains how the forecasts and their uncertainty ranges are made, why some of them failed, and what is and is not established. Numbers come from `results/` (files named in brackets). It is a portfolio project, not a production system.

## In plain English
The model learns, from almost ten years of past data, how electricity use in each of Germany's four grid zones depends on the hour of the day, the weekday, holidays, the season, the load a few days ago and (for the first days only, and only where it helped) the weather forecast. A separate model is trained for each "distance into the future", so that a model for day 7 never sees anything that would not yet be known 7 days ahead. Next to the best guess it produces ranges (80% and 95%) that are meant to contain the real value that often. Those ranges turned out too narrow on a year of data held back for the final test (they contained 72.5% and 90.8%), because the usual guarantee behind them assumes data that behave the same way over time, and electricity demand does not. For future days the ranges are now recalibrated on recent errors; that fix has only been checked on the validation year, and the real check is the one-off forecast made on 2026-11-11 (see the README, *Prospective check*).

## 1. The forecasting problem and the no-leakage setup
Let $y_t$ be the hourly load (MWh/h) of one zone at hour $t$. For a **forecast origin** $O$ (the last hour with a known load) we want $\hat y_t$ for $t = O+1,\dots,O+24\cdot 21$. Day $d$ is $(O+24(d-1),\,O+24d]$.

I use a **direct multi-horizon** scheme: one model $f_k$ per zone for $k\in\{1,2,3,5,7,10,14,16\}$ days (plus $k=21$ for a low-confidence outlook). Model $f_k$ predicts $y_t$ from

$$\hat y_t = f_k\big(c_t,\; y_{t-24k},\; y_{t-24k-24},\; y_{t-w},\; y_{t-w-168},\; \bar y^{(24)}_{t-24k},\; \bar y^{(168)}_{t-24k},\; \text{weather}_t\big),\qquad w=168\lceil 24k/168\rceil ,$$

where $c_t$ are calendar features (hour, weekday, month, day of year, holiday share, bridge day) and the bars are means over the known 24 and 168 hours. **Every load input lies at or before $t-24k$.** A target hour on forecast day $d$ is served by the smallest $k\ge d$, so it lies at most $24k$ hours after the origin and every load input is known at the origin (tested in `tests/test_horizon.py`). Weather inputs exist only for $k\le 7$ because the archive of past weather *forecasts* (Open-Meteo Previous Runs) only reaches 7 days of lead time; the model sees archived forecasts in training, the same kind of input as at serving time.

**Splits are by time only:** train before 2024-10-25, validation 2024-10-25 to 2025-10-24, final test 2025-10-25 to 2026-10-24. Tuning uses validation only.

## 2. Gradient boosting
Boosting builds an additive model

$$F_M(x)=F_0+\sum_{m=1}^{M}\nu\,h_m(x),$$

where each $h_m$ is a small regression tree and $\nu$ is a learning rate (here $0.05$, $M=600$). Given a loss $L(y,F)$, stage $m$ takes one step of functional gradient descent on the training loss $\sum_i L(y_i,F(x_i))$: compute the negative gradient at the current model,

$$r_{im}=-\left.\frac{\partial L(y_i,F)}{\partial F}\right|_{F=F_{m-1}(x_i)},$$

fit a tree $h_m$ to the pairs $(x_i,r_{im})$, and add it with a step size. For squared error $L=\tfrac12(y-F)^2$ the negative gradient is simply the residual $y_i-F_{m-1}(x_i)$, so each tree fits what the model still gets wrong (Friedman 2001). With other losses (the pinball loss below) the trees fit the corresponding gradient instead. This explains the name; it does not by itself guarantee good out-of-sample performance, which is why the learning rate is small and the validation year is used to judge it.

**What LightGBM changes** (Ke et al. 2017), in one paragraph: it bins each feature into a few hundred histogram buckets, so finding the best split costs a pass over bucket statistics rather than over sorted raw values; it grows trees **leaf-wise** (always splitting the leaf with the largest loss reduction, up to 31 leaves here) instead of level-by-level; and it uses first- and second-order gradient statistics to score splits and set leaf values. The row and column subsampling used here (80% each) is ordinary stochastic boosting.

## 3. Quantile (pinball) loss
For a level $\tau\in(0,1)$ the pinball loss is $\rho_\tau(u)=u\,(\tau-\mathbf 1\{u<0\})$ with $u=y-q$. For a random $Y$ with distribution function $F$,

$$\frac{d}{dq}\,\mathbb E\,\rho_\tau(Y-q)= -\tau\,\big(1-F(q)\big)+(1-\tau)\,F(q)=F(q)-\tau ,$$

which is zero exactly where $F(q)=\tau$: the minimiser is the $\tau$-quantile (Koenker and Bassett 1978). Training a boosted model with this loss therefore estimates a conditional quantile. I train models for $\tau\in\{0.025,0.1,0.5,0.9,0.975\}$; the 10%/90% pair is a nominal 80% range and 2.5%/97.5% a nominal 95% range. Raw quantile models were too narrow too (58.0% and 78.4% on the test year; `README`, *Prediction intervals*).

## 4. Split conformal prediction and conformalized quantile regression
Take a calibration set of $n$ points not used for training, a score $s_i$ that measures how badly an interval misses, and let $\hat Q$ be the $\lceil (n+1)(1-\alpha)\rceil/n$ empirical quantile of the scores. If calibration and new points are **exchangeable**, then $\Pr(Y_{\text{new}}\in C)\ge 1-\alpha$, where $C$ is the set of $y$ whose score is at most $\hat Q$ (Vovk, Gammerman and Shafer 2005). The guarantee is marginal (averaged over the calibration draw) and finite-sample.

For **conformalized quantile regression** (Romano, Patterson and Candès 2019) with lower and upper quantile predictions $\hat q_{lo},\hat q_{hi}$ the score is $s_i=\max\{\hat q_{lo}(x_i)-y_i,\;y_i-\hat q_{hi}(x_i)\}$ and the interval is $[\hat q_{lo}(x)-\hat Q,\;\hat q_{hi}(x)+\hat Q]$. This is what the map has used: one offset $\hat Q$ per zone, horizon and band, calibrated on the whole validation year (`models_future/cqr_offsets_future.json`).

## 5. Why it failed here, and what we saw
Time series are not exchangeable: demand follows seasons, holidays, economic conditions and weather regimes, and a score distribution measured in one year need not describe the next. Calibrated on the validation year, the offsets gave about 80% and 94% coverage when scored on the other half of the same year (`results/horizon_coverage_val.csv`), but **72.5% and 90.8%** on the following, sealed year (zones: TenneT 66.9% and 87.1%, 50Hertz 78.9% and 94.4%; `site/data/meta.json`). So the nominal level held under exchangeability, which was true by construction in that check, and not under a time shift, which is the case that matters.

## 6. Recalibrating on recent errors (validation replay; future days only)
Two ways to let the offset follow the data (details and rules: `results/EXPERIMENTS.md`, entry I1):

* **Rolling window.** Recompute $\hat Q$ from the scores of the last $N$ weeks only. A score is usable at hour $t$ only if its hour is at most $t-24k$ (the earliest origin of a horizon-$k$ forecast for $t$). The window $N\in\{4,8,13\}$ weeks was compared.
* **Adaptive conformal inference** (Gibbs and Candès 2021). Keep a working miscoverage level and update it online from the observed miss indicator $\mathrm{err}_t=\mathbf 1\{y_t\notin C_t\}$:
$$\alpha_{t+1}=\alpha_t+\gamma\,(\alpha-\mathrm{err}_t),$$
and use the $(1-\alpha_t)$ quantile of the known scores. After a run of misses $\alpha_t$ falls and the interval widens; after a run of hits it narrows. Under any sequence of data the long-run miss frequency is within $O\!\big(1/(\gamma T)\big)$ of $\alpha$ [verify the exact constant in the paper]. In my replay the feedback arrives $24k$ hours late, which the paper's setting does not include, so that guarantee does not carry over exactly. Step sizes $\gamma\in\{0.005,0.01,0.02\}$.

On the validation year (a 13-week burn-in, 274 scored days, one setting for every zone and horizon) the rolling windows kept coverage near 80% and 94% with cell-level worst cases of about 78% and 93%, while ACI had the smallest average gap but widened the intervals by so much that the pre-registered rule (interval score at most 10% worse than the fixed method) excluded it. The selection was `rolling_8w`. **Limits:** the fixed method in that replay is calibrated on only 13 weeks, so the comparison shows steadiness rather than a repair of the test-year failure; the choice among seven candidates and the scoring use the same validation year; and the validation year contained no shift as large as the test year.

At serving time the sealed test year may not be used, so the 8-week window could only be filled with the 16 days after it (392 hourly errors per cell). The resulting offsets are larger than the old ones in most cells. **Past dates on the map keep the old fixed ranges**, so past and future ranges come from different methods.

## 7. Metrics
**MAE** $=\frac1n\sum|y_t-\hat y_t|$ in MWh/h. **Coverage** is the share of actual values inside a range. **Mean width** is the average range length. The **interval score** (Gneiting and Raftery 2007) for a range $[l,u]$ at nominal level $1-\alpha$ is

$$S_\alpha=(u-l)+\tfrac{2}{\alpha}(l-y)^+ +\tfrac{2}{\alpha}(y-u)^+ ,$$

a proper score that charges for width and heavily for misses; lower is better.

## 8. Pre-registration and the sealed test, and their honest limits
Every experiment's rules (hypothesis, the single change, keep/revert criteria) were written in `results/EXPERIMENTS.md` before the results were seen, and the final test year was held in a separate file read by a one-shot script. In fact the test year **has been used twice** (once for the 24-hour model, once for the multi-day models), plus a few non-metric reads (map export, a missing-input count), all disclosed. Nothing was tuned on it, but it is no longer a clean untouched sample, and with many selection decisions made on validation some optimism in validation numbers is expected. The strongest evidence available is **prospective**: the forecast of 2026-11-11 was saved before the hours happened (SHA-256 in the README) and will be scored once SMARD has published the load; it will be reported whatever the outcome.

## 9. Limitations
* The ranges are too narrow on new data; the new method has been checked on validation data only.
* The 24-hour model is a *rolling* forecast (it knows the load of 24 hours earlier and uses observed weather), not a day-ahead forecast; comparisons with SMARD's day-ahead forecast are not like-for-like.
* The models were trained on data before 2024-10-25 and are about two years old; days 8 to 21 use no weather.
* Zones follow transmission-operator areas, not state borders; the state-to-zone assignment is a judgement.
* Several results rest on one validation year and one test year; hour-level errors are strongly autocorrelated, so effective sample sizes are much smaller than the hour counts.
* A model comparison (`results/model_comparison_val.csv`) found a small neural network about as accurate as LightGBM on validation; LightGBM was kept because the models were locked, not because it was shown to be better.

## References
* Friedman, J. H. (2001). Greedy function approximation: a gradient boosting machine. *Annals of Statistics* 29(5), 1189-1232.
* Gibbs, I. and Candès, E. (2021). Adaptive conformal inference under distribution shift. *Advances in Neural Information Processing Systems* 34.
* Gneiting, T. and Raftery, A. E. (2007). Strictly proper scoring rules, prediction, and estimation. *Journal of the American Statistical Association* 102(477), 359-378.
* Ke, G. et al. (2017). LightGBM: a highly efficient gradient boosting decision tree. *Advances in Neural Information Processing Systems* 30.
* Koenker, R. and Bassett, G. (1978). Regression quantiles. *Econometrica* 46(1), 33-50.
* Romano, Y., Patterson, E. and Candès, E. (2019). Conformalized quantile regression. *Advances in Neural Information Processing Systems* 32.
* Vovk, V., Gammerman, A. and Shafer, G. (2005). *Algorithmic Learning in a Random World*. Springer.

Page numbers and volume details above are from memory; check them before citing: [verify].
