
from matplotlib import pyplot as plt
from numba import guvectorize, float64, int64, vectorize


# battery_capacity = 5000  # in Watt hour
battery_in_efficiency = 0.8
battery_out_efficiency = 0.8
min_power_excess = 300  # in Watt
max_bat_power = 2500  # max (dis)charging power in Watt
max_charging_cycles = 6000
kwh_price = 0.39  # in euro


def get_instant_p1_values(time_from: str, time_to: str, resolution='1m'):
    df = None  # Your own query to fill a dataframe with columns `usage` and `delivery`that represent (instant) p1 power values (in Watt)
    return df


time_from = '2024-03-25T00:00:00Z'
time_to = '2025-03-25T00:00:00Z'
resolution = '1m'
if resolution not in ('1s', '1m', '1h'):
    raise ValueError("Unknown resolution: %s" % resolution)
nsec = 1 if resolution == '1s' else 60 if resolution == '1m' else 60 * 60

df = get_instant_p1_values(time_from, time_to, resolution=resolution)


@vectorize([float64(float64, int64)])
def p2e(power, nsec=nsec):
    return power * (nsec / 3600)
@vectorize([float64(float64, int64)])
def e2p(energy, nsec=nsec):
    return energy / (nsec / 3600)
@vectorize([float64(float64)])
def p2e(power):
    return p2e(power, nsec)
@vectorize([float64(float64)])
def e2p(energy):
    return e2p(energy, nsec)
@guvectorize([(float64[:], float64, float64[:], float64[:])], '(n),()->(n),(n)', nopython=True)
def simulate_batt_level(p1_netto, batt_cap, res, res2):
    res[0] = 0.0
    for i in range(1, len(p1_netto)):
        batt_level = res[i-1]
        p1_delta = 0.0
        if p1_netto[i] < 0:
            if batt_level < batt_cap:
                if p1_netto[i] < -min_power_excess:
                    p1_delta = min(abs(p1_netto[i]), e2p(batt_cap - batt_level), max_bat_power)
        else:
            if batt_level > 0:
                # if row['p1_netto'] > min_power_excess:
                p1_delta = -min(abs(p1_netto[i]), e2p(batt_level), max_bat_power)
        bat_delta = p2e(p1_delta)
        batt_level += bat_delta * battery_in_efficiency if bat_delta > 0 else bat_delta
        res[i] = batt_level
        res2[i] = p1_delta


df['p1_netto'] = df['usage'] - df['delivery']   # power in Watt

savings_kwh = {}
for battery_capacity in (1000*k for k in range(1, 10+1)):
    df['battery_level'], df['p1_delta'] = simulate_batt_level(df['p1_netto'], battery_capacity)
    df['p1_netto_sim'] = df['p1_netto'] + df['p1_delta'].mask(df['p1_delta'] < 0, df['p1_delta'] * battery_out_efficiency)

    total_withdraw = p2e(df['p1_netto'][df['p1_netto'] > 0]).sum()
    total_return = p2e(df['p1_netto'][df['p1_netto'] < 0]).sum()
    total_withdraw_sim = p2e(df['p1_netto_sim'][df['p1_netto'] > 0]).sum()
    total_return_sim = p2e(df['p1_netto_sim'][df['p1_netto'] < 0]).sum()

    print("Summary for battery capacity: %d" % battery_capacity)
    saved_withdrawn = (total_withdraw - total_withdraw_sim)
    print("Total saved withdraw: %0.3f kWh, on a total of %0.3f kWh" % (saved_withdrawn/1000, total_withdraw/1000))

    fig, ax = plt.subplots(2, 1, sharex=True, figsize=(30, 10))
    ax[0].plot(df['t0_sec'], df['p1_netto'], label='real')
    ax[0].plot(df['t0_sec'], df['p1_netto_sim'], label='simulated')
    ax[0].legend()
    ax[1].plot(df['t0_sec'], df['battery_level'], label='battery')
    plt.suptitle("Simulated battery capacity: %d. Total saved withdraw: %0.3f kWh, on a total of %0.3f kWh" %
                 (battery_capacity, saved_withdrawn/1000, total_withdraw/1000))
#    plt.show()
    plt.savefig('simulate_battery_%d.png' % battery_capacity)
    plt.close()

    savings_kwh[battery_capacity] = saved_withdrawn / 1000

# savings_kwh_year = {1000: 250.173, 3000: 587.449, 5000: 674.523, 10000: 708.383}
battery_life_year = max_charging_cycles / 365
savings_per_battery_life = {k: battery_life_year * v * kwh_price for k, v in savings_kwh.items()}
print("max_allowed_price_battery = %s" % str(savings_per_battery_life))
# max_allowed_price_battery = {1000: 1603.85, 3000: 3766.11, 5000: 4324.34, 10000: 4541.41}

fig, ax = plt.subplots(2,1, sharex=True)
ax[0].plot(savings_kwh.keys(), savings_kwh.values(), label='saving_kwh')
ax[0].set_title('saved kWh (per period)')
ax[1].plot(savings_per_battery_life.keys(), savings_per_battery_life.values(), label='savings_per_battery_life')
ax[1].set_title('allowed battery price to break even over battery life (%0.1f years)' % (max_charging_cycles/365))
fig.suptitle('Totals over period %s - %s' % (time_from[:len('yyyy-mm-dd')], time_to[:len('yyyy-mm-dd')]))
ax[1].set_xlabel('battery capacity (Wh)')
ax[0].set_ylabel('kWh')
ax[1].set_ylabel('euro')
plt.tight_layout()
plt.savefig('simulate_battery_totals.png')
plt.close()
print('done')
