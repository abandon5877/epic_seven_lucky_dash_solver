importScripts('success_rates.js');

class LuckyRushSolver {
    constructor(level, target, start_shield = 2, start_boost = 1, reward_weights = null) {
        this.target = target;
        this.start_shield = start_shield;
        this.start_boost = start_boost;
        this.reward_weights = reward_weights || { 100: 1, 200: 2, 300: 3, 350: 4, 450: 5 };
        this.success_rates = SUCCESS_RATES;
        this.lucky_levels = {
            1: { start_count: 1, max_count: 1, refill_point: 200, req_energy: 50 },
            2: { start_count: 1, max_count: 1, refill_point: 180, req_energy: 100 },
            3: { start_count: 1, max_count: 2, refill_point: 180, req_energy: 150 },
            4: { start_count: 1, max_count: 2, refill_point: 150, req_energy: 250 },
            5: { start_count: 2, max_count: 2, refill_point: 150, req_energy: 350 },
        };
        this.level = level;
        this.level_info = this.lucky_levels[level];
        this.refill_point = this.level_info.refill_point;
        this.max_lucky = this.level_info.max_count;
        this.start_lucky = this.level_info.start_count;
        this.energy_per_run = 1;
        this.energy_per_lucky = 3;
        this.memo_p = {};
        this.memo_e = {};
        this.memo_action = {};
        // 预计算缓存
        this._statesCache = null;
        this._rateCache = null;
    }
    get_success_rate(pos) {
        if (pos <= 0) return 1.0;
        // 优先查缓存
        if (this._rateCache && this._rateCache[pos] !== undefined) return this._rateCache[pos];
        let rate;
        if (this.success_rates[pos] !== undefined) {
            rate = this.success_rates[pos];
        } else {
            const distances = Object.keys(this.success_rates).map(Number).sort((a, b) => a - b);
            if (pos < distances[0]) {
                rate = this.success_rates[distances[0]];
            } else if (pos > distances[distances.length - 1]) {
                const d1 = distances[distances.length - 2];
                const d2 = distances[distances.length - 1];
                const r1 = this.success_rates[d1];
                const r2 = this.success_rates[d2];
                const slope = (r2 - r1) / (d2 - d1);
                rate = Math.max(0.05, r2 + slope * (pos - d2));
            } else {
                let lower = distances[0];
                let upper = distances[distances.length - 1];
                for (const d of distances) {
                    if (d <= pos && d > lower) lower = d;
                    if (d >= pos && d < upper) upper = d;
                }
                if (lower === upper) {
                    rate = this.success_rates[lower];
                } else {
                    const r_lower = this.success_rates[lower];
                    const r_upper = this.success_rates[upper];
                    rate = r_lower + (r_upper - r_lower) * (pos - lower) / (upper - lower);
                    rate = Math.max(0.0, Math.min(1.0, rate));
                }
            }
        }
        if (this._rateCache) this._rateCache[pos] = rate;
        return rate;
    }
    _buildRateCache() {
        // 预计算所有可能 pos 的成功率
        this._rateCache = {};
        for (let pos = 0; pos <= this.target + 30; pos += 10) {
            this._rateCache[pos] = this.get_success_rate(pos);
        }
        // 负数位置（助跑后退用）
        for (let pos = -10; pos < 0; pos += 10) {
            this._rateCache[pos] = 1.0;
        }
    }
    reward_at(pos) {
        let total = 0;
        for (const node of [100, 200, 300, 350, 450]) {
            if (pos >= node && this.reward_weights[node]) {
                total += this.reward_weights[node];
            }
        }
        return total;
    }
    milestone_rewards(old_pos, new_pos, shield, boost) {
        let new_shield = shield;
        let new_boost = boost;
        for (let milestone = 100; milestone <= new_pos; milestone += 100) {
            if (milestone > old_pos) {
                new_shield = Math.min(new_shield + 2, 4);
                new_boost += 1;
            }
        }
        return [new_shield, new_boost];
    }
    refill_lucky(old_pos, new_pos, lucky) {
        let new_lucky = lucky;
        for (let m = this.refill_point; m <= new_pos; m += this.refill_point) {
            if (old_pos < m) {
                new_lucky = Math.min(this.max_lucky, new_lucky + 1);
            }
        }
        return new_lucky;
    }
    cap_state(state) {
        const [pos, shield, boost, lucky] = state;
        const max_shield = 4;
        const max_boost = this.start_boost + Math.floor(this.target / 100);
        return [pos, Math.min(shield, max_shield), Math.min(boost, max_boost), Math.min(lucky, this.max_lucky)];
    }
    enumerate_states() {
        if (this._statesCache) return this._statesCache;
        const max_shield = 4;
        const max_boost = this.start_boost + Math.floor(this.target / 100);
        const states = [];
        for (let pos = 0; pos <= this.target; pos += 10) {
            for (let shield = 0; shield <= max_shield; shield++) {
                for (let boost = 0; boost <= max_boost; boost++) {
                    for (let lucky = 0; lucky <= this.max_lucky; lucky++) {
                        states.push([pos, shield, boost, lucky]);
                    }
                }
            }
        }
        this._statesCache = states;
        return states;
    }
    solve(start_state) {
        const states = this.enumerate_states();
        const P = {};
        const E = {};
        const action = {};
        
        for (const s of states) {
            const key = JSON.stringify(s);
            if (s[0] >= this.target) {
                P[key] = 1.0;
                E[key] = 0.0;
                action[key] = null;
            } else {
                P[key] = 0.0;
                E[key] = 0.0;
                action[key] = null;
            }
        }
        
        const max_iter = 2000;
        const eps = 1e-10;
        
        for (let iter = 0; iter < max_iter; iter++) {
            let max_diff = 0.0;
            
            for (const s of states) {
                const pos = s[0];
                if (pos >= this.target) continue;
                
                const key = JSON.stringify(s);
                const [, shield, boost, lucky] = s;
                
                let best_p = -1.0, best_e = Infinity, best_action = null;
                const q = Math.min(pos + 10, this.target);
                const rate = this.get_success_rate(pos);
                
                if (rate > 0) {
                    const [ns, nb] = this.milestone_rewards(pos, q, shield, boost);
                    const nl = this.refill_lucky(pos, q, lucky);
                    const success_state = this.cap_state([q, ns, nb, nl]);
                    const success_key = JSON.stringify(success_state);

                    // 普通奔跑失败 = 游戏结束 (P=0, E=0)，不回到起点
                    const p = rate * P[success_key];
                    const e = this.energy_per_run + rate * E[success_key];

                    if (p > best_p + 1e-12 || (Math.abs(p - best_p) <= 1e-12 && e < best_e - 1e-12)) {
                        best_p = p; best_e = e; best_action = ['run', q, false];
                    }
                }
                
                if (shield > 0 && rate > 0) {
                    const [ns_prot, nb_prot] = this.milestone_rewards(pos, q, shield - 1, boost);
                    const nl_prot = this.refill_lucky(pos, q, lucky);
                    const success_state_prot = this.cap_state([q, ns_prot, nb_prot, nl_prot]);
                    const fail_state = this.cap_state([pos, shield - 1, boost, lucky]);
                    
                    const success_key = JSON.stringify(success_state_prot);
                    const fail_key = JSON.stringify(fail_state);
                    
                    const p = rate * P[success_key] + (1 - rate) * P[fail_key];
                    const e = this.energy_per_run + rate * E[success_key] + (1 - rate) * E[fail_key];
                    
                    if (p > best_p + 1e-12 || (Math.abs(p - best_p) <= 1e-12 && e < best_e - 1e-12)) {
                        best_p = p; best_e = e; best_action = ['run', q, true];
                    }
                }
                
                if (boost > 0 && pos >= 10) {
                    const back_pos = pos - 10;
                    const boost_rate = this.get_success_rate(back_pos);
                    if (boost_rate > 0) {
                        const new_pos = Math.min(pos + 30, this.target);
                        const [ns_b, nb_b] = this.milestone_rewards(pos, new_pos, shield, boost - 1);
                        const nl_b = this.refill_lucky(pos, new_pos, lucky);
                        const success_state_b = this.cap_state([new_pos, ns_b, nb_b, nl_b]);
                        const success_key = JSON.stringify(success_state_b);

                        // 助跑失败 = 游戏结束 (P=0, E=0)，不回到起点
                        const p = boost_rate * P[success_key];
                        const e = this.energy_per_run + boost_rate * E[success_key];

                        if (p > best_p + 1e-12 || (Math.abs(p - best_p) <= 1e-12 && e < best_e - 1e-12)) {
                            best_p = p; best_e = e; best_action = ['boost'];
                        }
                    }
                }
                
                if (lucky > 0) {
                    const new_pos = Math.min(pos + 30, this.target);
                    const [ns_l, nb_l] = this.milestone_rewards(pos, new_pos, shield, boost);
                    const nl_l = this.refill_lucky(pos, new_pos, lucky - 1);
                    const success_state_l = this.cap_state([new_pos, ns_l, nb_l, nl_l]);
                    const success_key = JSON.stringify(success_state_l);
                    
                    const p = 1.0 * P[success_key];
                    const e = this.energy_per_lucky + E[success_key];
                    
                    if (p > best_p + 1e-12 || (Math.abs(p - best_p) <= 1e-12 && e < best_e - 1e-12)) {
                        best_p = p; best_e = e; best_action = ['lucky'];
                    }
                }
                
                if (best_action) {
                    const diff = Math.max(Math.abs(P[key] - best_p), Math.abs(E[key] - best_e));
                    max_diff = Math.max(max_diff, diff);
                    P[key] = best_p;
                    E[key] = best_e;
                    action[key] = best_action;
                }
            }
            
            if (max_diff < eps) break;
        }
        
        this.memo_p = P;
        this.memo_e = E;
        this.memo_action = action;
        
        const start_key = JSON.stringify(start_state);
        return [P[start_key], E[start_key]];
    }
    solve_lambda(start_state, lambda) {
        const states = this.enumerate_states();
        const F = {};
        const action = {};

        for (const s of states) {
            const key = JSON.stringify(s);
            F[key] = (s[0] >= this.target) ? -lambda : 1e6;
            action[key] = null;
        }

        const max_iter = 2000;
        const eps = 1e-10;

        for (let iter = 0; iter < max_iter; iter++) {
            let max_diff = 0.0;

            for (const state of states) {
                const pos = state[0];
                if (pos >= this.target) continue;

                const key = JSON.stringify(state);
                const [, shield, boost, lucky] = state;

                let best_f = Infinity, best_action = null;

                const q = Math.min(pos + 10, this.target);
                const rate = this.get_success_rate(pos);
                const actions_to_try = [];

                if (rate > 0) {
                    actions_to_try.push(['run', q, false]);
                    if (shield > 0) actions_to_try.push(['run', q, true]);
                }
                if (boost > 0 && pos >= 10) {
                    const boost_rate = this.get_success_rate(pos - 10);
                    if (boost_rate > 0) actions_to_try.push(['boost']);
                }
                if (lucky > 0) {
                    actions_to_try.push(['lucky']);
                }

                for (const act of actions_to_try) {
                    const r = this.immediate_success_rate(state, act);
                    const success_state = this.cap_state(this.get_success_state(state, act));
                    const success_key = JSON.stringify(success_state);
                    const cost = (act[0] === 'lucky') ? this.energy_per_lucky : this.energy_per_run;

                    let f_val;
                    if (act[0] === 'run' && !act[2] || act[0] === 'boost') {
                        // 普通奔跑/助跑失败 = 游戏结束，F=0
                        f_val = cost + r * F[success_key];
                    } else {
                        // 防护失败：留在原地继续
                        const fail_state = this.cap_state(this.get_failure_state(state, act));
                        const fail_key = JSON.stringify(fail_state);
                        f_val = cost + r * F[success_key] + (1 - r) * F[fail_key];
                    }

                    if (f_val < best_f - 1e-12) {
                        best_f = f_val; best_action = act;
                    }
                }

                if (best_action) {
                    const diff = Math.abs(F[key] - best_f);
                    max_diff = Math.max(max_diff, diff);
                    F[key] = best_f;
                    action[key] = best_action;
                }
            }

            if (max_diff < eps) break;
        }

        this.memo_f = F;
        this.memo_action = action;

        const start_key = JSON.stringify(start_state);
        return [F[start_key], action];
    }
    solve_reward_lambda(start_state, lambda) {
        const states = this.enumerate_states();
        const H = {};
        const action = {};

        for (const s of states) {
            const key = JSON.stringify(s);
            H[key] = (s[0] >= this.target) ? 0.0 : -1e6;
            action[key] = null;
        }

        const max_iter = 2000;
        const eps = 1e-10;

        for (let iter = 0; iter < max_iter; iter++) {
            let max_diff = 0.0;

            for (const state of states) {
                const pos = state[0];
                if (pos >= this.target) continue;

                const key = JSON.stringify(state);
                const [, shield, boost, lucky] = state;

                let best_h = -1e6, best_action = null;

                const q = Math.min(pos + 10, this.target);
                const rate = this.get_success_rate(pos);
                const actions_to_try = [];

                if (rate > 0) {
                    actions_to_try.push(['run', q, false]);
                    if (shield > 0) actions_to_try.push(['run', q, true]);
                }
                if (boost > 0 && pos >= 10) {
                    const boost_rate = this.get_success_rate(pos - 10);
                    if (boost_rate > 0) actions_to_try.push(['boost']);
                }
                if (lucky > 0) {
                    actions_to_try.push(['lucky']);
                }

                for (const act of actions_to_try) {
                    const r = this.immediate_success_rate(state, act);
                    const success_state = this.cap_state(this.get_success_state(state, act));
                    const success_key = JSON.stringify(success_state);
                    const cost = (act[0] === 'lucky') ? this.energy_per_lucky : this.energy_per_run;

                    let new_pos;
                    if (act[0] === 'run') new_pos = Math.min(pos + 10, this.target);
                    else new_pos = Math.min(pos + 30, this.target);
                    const reward_gain = this.reward_at(new_pos) - this.reward_at(pos);

                    let h_val;
                    if (act[0] === 'run' && !act[2] || act[0] === 'boost') {
                        h_val = r * reward_gain - lambda * cost + r * H[success_key];
                    } else if (act[0] === 'run' && act[2]) {
                        const fail_state = this.cap_state(this.get_failure_state(state, act));
                        const fail_key = JSON.stringify(fail_state);
                        h_val = r * reward_gain - lambda * cost + r * H[success_key] + (1 - r) * H[fail_key];
                    } else {
                        h_val = reward_gain - lambda * cost + H[success_key];
                    }

                    if (h_val > best_h + 1e-12) {
                        best_h = h_val; best_action = act;
                    }
                }

                if (best_action) {
                    const diff = Math.abs(H[key] - best_h);
                    max_diff = Math.max(max_diff, diff);
                    H[key] = best_h;
                    action[key] = best_action;
                }
            }

            if (max_diff < eps) break;
        }

        this.memo_h = H;
        this.memo_action = action;

        const start_key = JSON.stringify(start_state);
        return [H[start_key], action];
    }
    evaluate_policy(policy, start_state) {
        const states = this.enumerate_states();
        const P = {};
        const E = {};

        for (const s of states) {
            const key = JSON.stringify(s);
            if (s[0] >= this.target) {
                P[key] = 1.0;
                E[key] = 0.0;
            } else {
                P[key] = 0.0;
                E[key] = 0.0;
            }
        }

        const max_iter = 2000;
        const eps = 1e-10;

        for (let iter = 0; iter < max_iter; iter++) {
            let max_diff = 0.0;

            for (const state of states) {
                const pos = state[0];
                if (pos >= this.target) continue;

                const key = JSON.stringify(state);
                const action = policy[key];
                if (!action) continue;

                const rate = this.immediate_success_rate(state, action);
                const success_state = this.cap_state(this.get_success_state(state, action));
                const success_key = JSON.stringify(success_state);
                const cost = (action[0] === 'lucky') ? this.energy_per_lucky : this.energy_per_run;

                let new_p, new_e;
                if (action[0] === 'run' && !action[2] || action[0] === 'boost') {
                    // 普通奔跑/助跑失败 = 游戏结束，P=0, E=0
                    new_p = rate * P[success_key];
                    new_e = cost + rate * E[success_key];
                } else {
                    // 防护失败：留在原地继续
                    const fail_state = this.cap_state(this.get_failure_state(state, action));
                    const fail_key = JSON.stringify(fail_state);
                    new_p = rate * P[success_key] + (1 - rate) * P[fail_key];
                    new_e = cost + rate * E[success_key] + (1 - rate) * E[fail_key];
                }

                const diff = Math.max(Math.abs(P[key] - new_p), Math.abs(E[key] - new_e));
                max_diff = Math.max(max_diff, diff);
                P[key] = new_p;
                E[key] = new_e;
            }

            if (max_diff < eps) break;
        }

        const start_key = JSON.stringify(start_state);
        return [P[start_key], E[start_key]];
    }
    evaluate_policy_reward(policy, start_state) {
        // 对固定策略，值迭代求 R[start] 和 E[start]（max_reward 模式专用）
        // R = 期望累计边际奖励；E = 期望累计能量
        const states = this.enumerate_states();
        const R = {};
        const E = {};

        for (const s of states) {
            const key = JSON.stringify(s);
            if (s[0] >= this.target) {
                R[key] = 0.0;
                E[key] = 0.0;
            } else {
                R[key] = 0.0;
                E[key] = 0.0;
            }
        }

        const max_iter = 2000;
        const eps = 1e-10;

        for (let iter = 0; iter < max_iter; iter++) {
            let max_diff = 0.0;

            for (const state of states) {
                const pos = state[0];
                if (pos >= this.target) continue;

                const key = JSON.stringify(state);
                const action = policy[key];
                if (!action) continue;

                const rate = this.immediate_success_rate(state, action);
                const success_state = this.cap_state(this.get_success_state(state, action));
                const success_key = JSON.stringify(success_state);
                const cost = (action[0] === 'lucky') ? this.energy_per_lucky : this.energy_per_run;

                let new_pos;
                if (action[0] === 'run') new_pos = Math.min(pos + 10, this.target);
                else new_pos = Math.min(pos + 30, this.target);
                const reward_gain = this.reward_at(new_pos) - this.reward_at(pos);

                let new_r, new_e;
                if (action[0] === 'run' && !action[2] || action[0] === 'boost') {
                    // 普通奔跑/助跑失败 = 游戏结束，未来 R=0, E=0
                    new_r = rate * (reward_gain + R[success_key]);
                    new_e = cost + rate * E[success_key];
                } else if (action[0] === 'run' && action[2]) {
                    // 防护失败：留在原地继续
                    const fail_state = this.cap_state(this.get_failure_state(state, action));
                    const fail_key = JSON.stringify(fail_state);
                    new_r = rate * (reward_gain + R[success_key]) + (1 - rate) * R[fail_key];
                    new_e = cost + rate * E[success_key] + (1 - rate) * E[fail_key];
                } else {
                    // 超级幸运 rate=1
                    new_r = reward_gain + R[success_key];
                    new_e = cost + E[success_key];
                }

                const diff = Math.max(Math.abs(R[key] - new_r), Math.abs(E[key] - new_e));
                max_diff = Math.max(max_diff, diff);
                R[key] = new_r;
                E[key] = new_e;
            }

            if (max_diff < eps) break;
        }

        const start_key = JSON.stringify(start_state);
        return [R[start_key], E[start_key]];
    }
    evaluate_node_crossing_probabilities(policy, start_state, nodes = [100, 200, 300, 350, 450]) {
        // 对固定策略，一次值迭代同时求所有节点 n 的 V_n[start] = P(本局跨过 n)
        // 优化：合并 5 次独立值迭代为 1 次，状态键/转移只计算一次
        const states = this.enumerate_states();
        const numNodes = nodes.length;
        // V[ni][key] = 节点 ni 的跨越概率
        const V = new Array(numNodes);
        for (let ni = 0; ni < numNodes; ni++) {
            V[ni] = {};
            for (const s of states) V[ni][JSON.stringify(s)] = 0.0;
        }

        const max_iter = 2000;
        const eps = 1e-10;

        for (let iter = 0; iter < max_iter; iter++) {
            let max_diff = 0.0;

            for (const state of states) {
                const pos = state[0];
                if (pos >= this.target) continue;

                const key = JSON.stringify(state);
                const action = policy[key];
                if (!action) continue;

                const rate = this.immediate_success_rate(state, action);
                const success_state = this.cap_state(this.get_success_state(state, action));
                const success_key = JSON.stringify(success_state);

                let new_pos;
                if (action[0] === 'run') new_pos = Math.min(pos + 10, this.target);
                else new_pos = Math.min(pos + 30, this.target);

                const isProt = action[0] === 'run' && action[2];
                let fail_key = null;
                if (isProt) {
                    const fail_state = this.cap_state(this.get_failure_state(state, action));
                    fail_key = JSON.stringify(fail_state);
                }

                for (let ni = 0; ni < numNodes; ni++) {
                    const n = nodes[ni];
                    if (pos >= n) continue;  // 已跨过 n

                    let new_v;
                    if (new_pos >= n) {
                        // 本步成功则跨过 n
                        if (isProt) {
                            new_v = rate * 1.0 + (1 - rate) * V[ni][fail_key];
                        } else {
                            // 普通奔跑/助跑失败：游戏结束，未跨过=0
                            new_v = rate * 1.0;
                        }
                    } else {
                        if (isProt) {
                            new_v = rate * V[ni][success_key] + (1 - rate) * V[ni][fail_key];
                        } else {
                            new_v = rate * V[ni][success_key];
                        }
                    }

                    const diff = Math.abs(V[ni][key] - new_v);
                    if (diff > max_diff) max_diff = diff;
                    V[ni][key] = new_v;
                }
            }

            if (max_diff < eps) break;
        }

        const result = {};
        const start_key = JSON.stringify(start_state);
        for (let ni = 0; ni < numNodes; ni++) {
            result[nodes[ni]] = V[ni][start_key];
        }
        return result;
    }
    solve_min_ep(max_iter = 50, eps = 1e-9) {
        let lam = 0.0;
        let best_policy = null;
        let best_p = 0.0, best_e = Infinity;
        const start_state = [0, this.start_shield, this.start_boost, this.start_lucky];

        for (let i = 0; i < max_iter; i++) {
            const [F, policy] = this.solve_lambda(start_state, lam);
            const [p, e] = this.evaluate_policy(policy, start_state);
            if (p <= 1e-12) break;
            const new_lam = e / p;
            best_p = p; best_e = e; best_policy = policy;
            if (Math.abs(new_lam - lam) < eps) break;
            lam = new_lam;
        }
        return [best_p, best_e, best_policy];
    }
    solve_max_reward_per_energy(max_iter = 50, eps = 1e-9) {
        // Dinkelbach 主循环：最大化 R/E
        let lam = 0.0;
        let best_policy = null;
        let best_r = 0.0, best_e = 0.0;
        const start_state = [0, this.start_shield, this.start_boost, this.start_lucky];

        for (let i = 0; i < max_iter; i++) {
            const [H, policy] = this.solve_reward_lambda(start_state, lam);
            const [r, e] = this.evaluate_policy_reward(policy, start_state);
            if (e <= 1e-12) break;
            const new_lam = r / e;
            best_r = r; best_e = e; best_policy = policy;
            if (Math.abs(new_lam - lam) < eps) break;
            lam = new_lam;
        }
        return [best_r, best_e, best_policy];
    }
    immediate_success_rate(state, action) {
        const [pos] = state;
        if (action[0] === 'run') return this.get_success_rate(pos);
        if (action[0] === 'boost') return this.get_success_rate(pos - 10);
        if (action[0] === 'lucky') return 1.0;
        return 0.0;
    }
    get_success_state(state, action) {
        const [pos, shield, boost, lucky] = state;
        if (action[0] === 'run') {
            const new_pos = Math.min(pos + 10, this.target);
            const used_shield = action[2] ? shield - 1 : shield;
            const [ns, nb] = this.milestone_rewards(pos, new_pos, used_shield, boost);
            const nl = this.refill_lucky(pos, new_pos, lucky);
            return [new_pos, ns, nb, nl];
        }
        if (action[0] === 'boost') {
            const new_pos = Math.min(pos + 30, this.target);
            const [ns, nb] = this.milestone_rewards(pos, new_pos, shield, boost - 1);
            const nl = this.refill_lucky(pos, new_pos, lucky);
            return [new_pos, ns, nb, nl];
        }
        if (action[0] === 'lucky') {
            const new_pos = Math.min(pos + 30, this.target);
            const [ns, nb] = this.milestone_rewards(pos, new_pos, shield, boost);
            const nl = this.refill_lucky(pos, new_pos, lucky - 1);
            return [new_pos, ns, nb, nl];
        }
        return state;
    }
    get_failure_state(state, action) {
        const [pos, shield, boost, lucky] = state;
        if (action[0] === 'run') {
            if (action[2]) {
                // 防护失败：留在原地，shield-1
                return [pos, shield - 1, boost, lucky];
            } else {
                // 普通奔跑失败：游戏结束
                return null;
            }
        }
        if (action[0] === 'boost') {
            // 助跑失败：游戏结束
            return null;
        }
        if (action[0] === 'lucky') {
            // 超级幸运不会失败
            return state;
        }
        return state;
    }
    build_tree(state, policy, depth, parent_cumulative_rate, fail_depth = 0) {
        const [pos, shield, boost, lucky] = state;

        // 递归终止：到达目标
        if (pos >= this.target) {
            return {
                type: 'target',
                state: state,
                action: null,
                rate: 1.0,
                cumulative_rate: parent_cumulative_rate,
                progress: 100,
                is_branching: false,
                success: null,
                failure: null
            };
        }

        // 递归终止：超过最大深度
        if (depth >= 50) {
            return {
                type: 'end',
                state: state,
                action: null,
                rate: 0.0,
                cumulative_rate: parent_cumulative_rate,
                progress: pos / this.target * 100,
                is_branching: false,
                success: null,
                failure: null
            };
        }

        const key = JSON.stringify(state);
        const action = policy[key] || this.memo_action[key];

        // 递归终止：无动作
        if (!action) {
            return {
                type: 'end',
                state: state,
                action: null,
                rate: 0.0,
                cumulative_rate: parent_cumulative_rate,
                progress: pos / this.target * 100,
                is_branching: false,
                success: null,
                failure: null
            };
        }

        const rate = this.immediate_success_rate(state, action);
        const success_state = this.cap_state(this.get_success_state(state, action));
        const is_branching = (action[0] === 'run' && action[2]);

        // 成功子树：累计成功率 = parent_cumulative × rate，重置 fail_depth
        const success_cumulative = parent_cumulative_rate * rate;
        const success_subtree = this.build_tree(success_state, policy, depth + 1, success_cumulative, 0);

        // 失败子树
        let failure_subtree = null;
        if (is_branching) {
            // 防护奔跑失败 → 递归构建失败子树（防护上限4层）
            const fail_state = this.cap_state(this.get_failure_state(state, action));
            const failure_cumulative = parent_cumulative_rate * (1 - rate);
            if (fail_depth < 4) {
                failure_subtree = this.build_tree(fail_state, policy, depth + 1, failure_cumulative, fail_depth + 1);
            } else {
                failure_subtree = {
                    type: 'end',
                    state: fail_state,
                    action: null,
                    rate: 0.0,
                    cumulative_rate: failure_cumulative,
                    progress: fail_state[0] / this.target * 100,
                    is_branching: false,
                    success: null,
                    failure: null
                };
            }
        } else if (action[0] === 'run' && !action[2] || action[0] === 'boost') {
            // 普通奔跑/助跑失败 → 游戏结束（终结节点，不递归）
            failure_subtree = {
                type: 'end',
                state: [0, 0, 0, 0],
                action: null,
                rate: 0.0,
                cumulative_rate: parent_cumulative_rate * (1 - rate),
                progress: 0,
                is_branching: false,
                success: null,
                failure: null,
                label: '游戏结束'
            };
        }
        // lucky: rate = 1.0，无失败分支，failure_subtree 保持 null

        return {
            type: 'node',
            state: state,
            action: action,
            rate: rate,
            cumulative_rate: parent_cumulative_rate,
            progress: pos / this.target * 100,
            is_branching: is_branching,
            success: success_subtree,
            failure: failure_subtree
        };
    }
    monte_carlo_simulate(n_simulations = 100000) {
        let successes = 0;
        let total_energy = 0.0;
        let success_energy = 0.0;

        for (let i = 0; i < n_simulations; i++) {
            let state = [0, this.start_shield, this.start_boost, this.start_lucky];
            let energy = 0;
            let game_over = false;

            while (!game_over) {
                const pos = state[0];
                if (pos >= this.target) {
                    successes++;
                    total_energy += energy;
                    success_energy += energy;
                    break;
                }

                const key = JSON.stringify(state);
                const action = this.memo_action[key];
                if (!action) break;

                const rate = this.immediate_success_rate(state, action);
                const cost = (action[0] === 'lucky') ? this.energy_per_lucky : this.energy_per_run;
                energy += cost;

                if (Math.random() < rate) {
                    state = this.cap_state(this.get_success_state(state, action));
                } else {
                    if (action[0] === 'run' && action[2]) {
                        // 防护奔跑失败：留在原地
                        state = this.cap_state(this.get_failure_state(state, action));
                    } else {
                        // 普通奔跑/助跑失败：游戏结束
                        total_energy += energy;
                        game_over = true;
                    }
                }
            }
        }

        const empirical_p = successes / n_simulations;
        const empirical_e = total_energy / n_simulations;
        const empirical_e_given_success = successes > 0 ? success_energy / successes : Infinity;
        return [empirical_p, empirical_e, empirical_e_given_success];
    }
    monte_carlo_reward_simulate(energy_budget) {
        // 在能量预算内反复游戏，统计各装备件数、总奖励、实际消耗能量、总局数
        const counts = { 100: 0, 200: 0, 300: 0, 350: 0, 450: 0 };
        let energy_used = 0;
        let games = 0;
        let total_reward = 0;

        while (energy_used < energy_budget) {
            let state = [0, this.start_shield, this.start_boost, this.start_lucky];
            let game_over = false;
            games++;

            while (!game_over && energy_used < energy_budget) {
                const pos = state[0];
                if (pos >= this.target) {
                    // 通关，开新局
                    break;
                }

                const key = JSON.stringify(state);
                const action = this.memo_action[key];
                if (!action) break;

                const rate = this.immediate_success_rate(state, action);
                const cost = (action[0] === 'lucky') ? this.energy_per_lucky : this.energy_per_run;

                if (energy_used + cost > energy_budget) {
                    // 能量不够，结束模拟
                    game_over = true;
                    break;
                }
                energy_used += cost;

                if (Math.random() < rate) {
                    const old_pos = pos;
                    state = this.cap_state(this.get_success_state(state, action));
                    const new_pos = state[0];
                    for (const node of [100, 200, 300, 350, 450]) {
                        if (new_pos >= node && old_pos < node && this.reward_weights[node]) {
                            counts[node]++;
                            total_reward += this.reward_weights[node];
                        }
                    }
                } else {
                    if (action[0] === 'run' && action[2]) {
                        state = this.cap_state(this.get_failure_state(state, action));
                    } else {
                        game_over = true;
                    }
                }
            }
        }

        return { counts, total_reward, energy_used, games };
    }
}

function handleMessage(e) {
    const { level, target, objective, mc_validate, n_simulations, reward_weights } = e.data;
    try {
        // max_reward 模式强制 target=450（硬上限）
        const effective_target = (objective === 'max_reward') ? 450 : target;
        const solver = new LuckyRushSolver(level, effective_target, 2, 1, reward_weights);
        // 预构建缓存（成功率表、状态空间）
        solver._buildRateCache();
        solver.enumerate_states();
        let p, e_val, policy, r_val = null, node_probs = null;

        if (objective === 'max_p') {
            [p, e_val] = solver.solve([0, solver.start_shield, solver.start_boost, solver.start_lucky]);
            policy = solver.memo_action;
        } else if (objective === 'max_reward') {
            [r_val, e_val, policy] = solver.solve_max_reward_per_energy();
            // 单独求 P 用于显示
            [p] = solver.evaluate_policy(policy, [0, solver.start_shield, solver.start_boost, solver.start_lucky]);
            // 各节点跨越概率（用于预计装备件数）
            node_probs = solver.evaluate_node_crossing_probabilities(policy, [0, solver.start_shield, solver.start_boost, solver.start_lucky]);
        } else {
            [p, e_val, policy] = solver.solve_min_ep();
        }

        const tree = solver.build_tree([0, solver.start_shield, solver.start_boost, solver.start_lucky], policy, 0, 1.0);

        let mc_result = null;
        if (mc_validate) {
            if (objective === 'max_reward') {
                const energy_budget = n_simulations || 100000;
                const mc_reward = solver.monte_carlo_reward_simulate(energy_budget);
                mc_result = { type: 'reward', counts: mc_reward.counts, total_reward: mc_reward.total_reward, energy_used: mc_reward.energy_used, games: mc_reward.games, energy_budget };
            } else {
                const n = n_simulations || 100000;
                const [mc_p, mc_e, mc_e_s] = solver.monte_carlo_simulate(n);
                mc_result = { type: 'ep', mc_p, mc_e, mc_e_given_success: mc_e_s, n_simulations: n };
            }
        }

        self.postMessage({
            success: true,
            p: p,
            e_val: e_val,
            r_val: r_val,
            node_probs: node_probs,
            tree: tree,
            memo_action: policy,
            start_shield: solver.start_shield,
            start_boost: solver.start_boost,
            start_lucky: solver.start_lucky,
            target: effective_target,
            mc_result: mc_result
        });
    } catch (err) {
        self.postMessage({
            success: false,
            error: err.message
        });
    }
}

self.onmessage = handleMessage;
