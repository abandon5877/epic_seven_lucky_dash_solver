class LuckyRushSolver:
    """
    幸运冲刺最优策略求解器。

    假设：
    - 普通奔跑每步固定前进 10 米（最后一步直接到达目标）。
    - 成功率按“起点位置”查表；0m 起步成功率为 100%。
    - 普通奔跑每次消耗 1 个能量饮料；超级幸运每次消耗 3 个能量饮料。
    - 每前进一步后，对跨过的每个 100 米节点补充 2 次防护 + 1 次助跑。
    - 到达超级幸运补充节点时，超级幸运次数补满至最大数量。
    - 失败（未使用防护）返回起点并重置所有特殊功能与路线奖励。
    - 初始防护、助跑数量默认为 2、1（与当前账号状态一致）。
    """

    def __init__(self, level, target, start_shield=2, start_boost=1, reward_weights=None):
        self.target = target
        self.start_shield = start_shield
        self.start_boost = start_boost
        self.reward_weights = reward_weights or {100: 1, 200: 2, 300: 3, 350: 4, 450: 5}

        self.success_rates = {
            0: 1.0, 10: 0.96, 20: 0.92, 30: 0.88, 40: 0.84, 50: 0.80,
            60: 0.75, 70: 0.70, 80: 0.65, 90: 0.60, 100: 0.75,
            110: 0.69, 120: 0.63, 130: 0.56, 140: 0.50, 150: 0.70,
            160: 0.64, 170: 0.58, 180: 0.51, 190: 0.45, 200: 0.67,
            210: 0.61, 220: 0.55, 230: 0.49, 240: 0.43, 250: 0.63,
            260: 0.58, 270: 0.52, 280: 0.46, 290: 0.41, 300: 0.60,
            310: 0.55, 320: 0.49, 330: 0.43, 340: 0.37, 350: 0.57,
            360: 0.52, 370: 0.47, 380: 0.42, 390: 0.37, 400: 0.54,
            410: 0.49, 420: 0.44, 430: 0.39, 440: 0.35, 450: 0.51,
            460: 0.47, 470: 0.425, 480: 0.38,
        }

        self.lucky_levels = {
            1: {"start_count": 1, "max_count": 1, "refill_point": 200, "req_energy": 50},
            2: {"start_count": 1, "max_count": 1, "refill_point": 180, "req_energy": 100},
            3: {"start_count": 1, "max_count": 2, "refill_point": 180, "req_energy": 150},
            4: {"start_count": 1, "max_count": 2, "refill_point": 150, "req_energy": 250},
            5: {"start_count": 2, "max_count": 2, "refill_point": 150, "req_energy": 350},
        }

        if level not in self.lucky_levels:
            raise ValueError("超级幸运等级必须在 1-5 之间")

        self.level = level
        self.level_info = self.lucky_levels[level]
        self.refill_point = self.level_info["refill_point"]
        self.max_lucky = self.level_info["max_count"]
        self.start_lucky = self.level_info["start_count"]

        self.energy_per_run = 1
        self.energy_per_lucky = 3

        # 手动 memo，因为 state 是 tuple 足够 hashable
        self.memo_p = {}
        self.memo_e = {}
        self.memo_action = {}

    def get_success_rate(self, pos):
        """获取到达指定位置的成功率，支持表格外插值。"""
        if pos <= 0:
            return 1.0
        if pos in self.success_rates:
            return self.success_rates[pos]

        distances = sorted(self.success_rates.keys())
        if pos < distances[0]:
            return self.success_rates[distances[0]]
        if pos > distances[-1]:
            # 超过表格最大距离，用最后两个已知点斜率外推，保底 5%
            d1, d2 = distances[-2], distances[-1]
            r1, r2 = self.success_rates[d1], self.success_rates[d2]
            slope = (r2 - r1) / (d2 - d1)
            return max(0.05, r2 + slope * (pos - d2))

        # 线性插值
        lower = max([d for d in distances if d <= pos], default=distances[0])
        upper = min([d for d in distances if d >= pos], default=distances[-1])
        if lower == upper:
            return self.success_rates[lower]
        r_lower = self.success_rates[lower]
        r_upper = self.success_rates[upper]
        rate = r_lower + (r_upper - r_lower) * (pos - lower) / (upper - lower)
        return max(0.0, min(1.0, rate))

    def reward_at(self, pos):
        """返回位置 pos 的累计奖励（跨过的所有奖励节点权重之和）。"""
        total = 0
        for node in [100, 200, 300, 350, 450]:
            if pos >= node and self.reward_weights.get(node):
                total += self.reward_weights[node]
        return total

    def milestone_rewards(self, old_pos, new_pos, shield, boost):
        """根据跨过的 100 米节点补充防护和助跑。"""
        new_shield = shield
        new_boost = boost
        for milestone in range(100, int(new_pos) + 1, 100):
            if milestone > old_pos:
                new_shield = min(new_shield + 2, 4)
                new_boost += 1
        return new_shield, new_boost

    def refill_lucky(self, old_pos, new_pos, lucky):
        """判断是否触发超级幸运补充节点：补充 1 次，不超过最大数量。"""
        if new_pos >= self.refill_point and old_pos < self.refill_point:
            return min(self.max_lucky, lucky + 1)
        return lucky

    def get_actions(self, state):
        """返回某状态下所有可行的动作。"""
        pos, shield, boost, lucky = state
        actions = []
        if pos >= self.target:
            return actions

        # 普通奔跑（不带防护 / 带防护）
        q = min(pos + 10, self.target)
        if self.get_success_rate(pos) > 0:
            actions.append(('run', q, False))
            if shield > 0:
                actions.append(('run', q, True))

        # 助跑
        if boost > 0 and pos >= 10:
            actions.append(('boost',))

        # 超级幸运
        if lucky > 0:
            actions.append(('lucky',))

        return actions

    def action_cost(self, action):
        """返回动作的能量消耗。"""
        if action[0] == 'lucky':
            return self.energy_per_lucky
        return self.energy_per_run

    def cap_state(self, state):
        """把状态资源数量限制在合理上界内（用于值迭代）。"""
        pos, shield, boost, lucky = state
        max_shield = 4
        max_boost = self.start_boost + 1 * (self.target // 100)
        return (
            pos,
            min(shield, max_shield),
            min(boost, max_boost),
            min(lucky, self.max_lucky)
        )

    def enumerate_states(self):
        """枚举值迭代用到的所有状态。"""
        max_shield = 4
        max_boost = self.start_boost + 1 * (self.target // 100)
        states = []
        for pos in range(0, self.target + 1, 10):
            for shield in range(max_shield + 1):
                for boost in range(max_boost + 1):
                    for lucky in range(self.max_lucky + 1):
                        states.append((pos, shield, boost, lucky))
        return states

    def solve(self, start_state=None):
        """
        使用值迭代算法计算最大成功概率和期望能量消耗。
        返回 (P, E)。
        """
        if start_state is None:
            start_state = (0, self.start_shield, self.start_boost, self.start_lucky)
        
        states = self.enumerate_states()
        
        P = {s: 0.0 for s in states}
        E = {s: 0.0 for s in states}
        action = {s: None for s in states}
        
        for s in states:
            if s[0] >= self.target:
                P[s] = 1.0
                E[s] = 0.0
                action[s] = None
        
        max_iter = 2000
        eps = 1e-10
        
        for _ in range(max_iter):
            max_diff = 0.0
            
            for s in states:
                pos = s[0]
                if pos >= self.target:
                    continue
                
                shield, boost, lucky = s[1], s[2], s[3]
                
                best_p = -1.0
                best_e = float('inf')
                best_action = None
                
                q = min(pos + 10, self.target)
                rate = self.get_success_rate(pos)
                
                if rate > 0:
                    ns, nb = self.milestone_rewards(pos, q, shield, boost)
                    nl = self.refill_lucky(pos, q, lucky)
                    success_state = (q, ns, nb, nl)
                    success_state = self.cap_state(success_state)

                    # 普通奔跑失败 = 游戏结束，P=0, E=0
                    p = rate * P[success_state]
                    e = self.energy_per_run + rate * E[success_state]

                    if p > best_p + 1e-12 or (abs(p - best_p) <= 1e-12 and e < best_e - 1e-12):
                        best_p, best_e, best_action = p, e, ('run', q, False)
                
                if shield > 0 and rate > 0:
                    ns_prot, nb_prot = self.milestone_rewards(pos, q, shield - 1, boost)
                    nl_prot = self.refill_lucky(pos, q, lucky)
                    success_state_prot = (q, ns_prot, nb_prot, nl_prot)
                    success_state_prot = self.cap_state(success_state_prot)
                    fail_state = (pos, shield - 1, boost, lucky)
                    fail_state = self.cap_state(fail_state)
                    
                    p = rate * P[success_state_prot] + (1 - rate) * P[fail_state]
                    e = self.energy_per_run + rate * E[success_state_prot] + (1 - rate) * E[fail_state]
                    
                    if p > best_p + 1e-12 or (abs(p - best_p) <= 1e-12 and e < best_e - 1e-12):
                        best_p, best_e, best_action = p, e, ('run', q, True)
                
                if boost > 0 and pos >= 10:
                    back_pos = pos - 10
                    boost_rate = self.get_success_rate(back_pos)
                    if boost_rate > 0:
                        new_pos = min(pos + 30, self.target)
                        ns_b, nb_b = self.milestone_rewards(pos, new_pos, shield, boost - 1)
                        nl_b = self.refill_lucky(pos, new_pos, lucky)
                        success_state_b = (new_pos, ns_b, nb_b, nl_b)
                        success_state_b = self.cap_state(success_state_b)

                        # 助跑失败 = 游戏结束，P=0, E=0
                        p = boost_rate * P[success_state_b]
                        e = self.energy_per_run + boost_rate * E[success_state_b]

                        if p > best_p + 1e-12 or (abs(p - best_p) <= 1e-12 and e < best_e - 1e-12):
                            best_p, best_e, best_action = p, e, ('boost',)
                
                if lucky > 0:
                    new_pos = min(pos + 30, self.target)
                    ns_l, nb_l = self.milestone_rewards(pos, new_pos, shield, boost)
                    nl_l = self.refill_lucky(pos, new_pos, lucky - 1)
                    success_state_l = (new_pos, ns_l, nb_l, nl_l)
                    success_state_l = self.cap_state(success_state_l)
                    
                    p = 1.0 * P[success_state_l]
                    e = self.energy_per_lucky + E[success_state_l]
                    
                    if p > best_p + 1e-12 or (abs(p - best_p) <= 1e-12 and e < best_e - 1e-12):
                        best_p, best_e, best_action = p, e, ('lucky',)
                
                if best_action:
                    diff = max(abs(P[s] - best_p), abs(E[s] - best_e))
                    max_diff = max(max_diff, diff)
                    P[s] = best_p
                    E[s] = best_e
                    action[s] = best_action
            
            if max_diff < eps:
                break
        
        self.memo_p = P
        self.memo_e = E
        self.memo_action = action
        
        return P[start_state], E[start_state]

    def solve_from_start(self):
        start_state = (0, self.start_shield, self.start_boost, self.start_lucky)
        return self.solve(start_state)

    def solve_lambda(self, lam, max_iter=2000, eps=1e-10):
        """对给定 λ，用值迭代求解 min F = E - λP（单次尝试意义下），返回 (F, policy)。"""
        states = self.enumerate_states()
        BIG = 1e6
        # 到达目标：E=0, P=1，所以 F = -λ
        F = {s: (-lam) if s[0] >= self.target else BIG for s in states}
        policy = {s: None for s in states}

        for _ in range(max_iter):
            max_diff = 0.0
            for s in states:
                pos = s[0]
                if pos >= self.target:
                    continue
                best_f = float('inf')
                best_action = None
                for action in self.get_actions(s):
                    cost = self.action_cost(action)
                    success_state = self.cap_state(self.get_success_state(s, action))
                    rate = self.immediate_success_rate(s, action)

                    # 普通奔跑/助跑失败：本次尝试结束，后续 F=0
                    if action[0] in ('run', 'boost') and not (action[0] == 'run' and action[2]):
                        f_val = cost + rate * F.get(success_state, BIG)
                    else:
                        # 防护失败：留在原地继续本次尝试
                        fail_state = self.cap_state(self.get_failure_state(s, action))
                        f_val = cost + rate * F.get(success_state, BIG) + (1 - rate) * F.get(fail_state, BIG)

                    if f_val < best_f - 1e-12:
                        best_f = f_val
                        best_action = action
                if best_f < float('inf'):
                    diff = abs(F[s] - best_f)
                    if diff > max_diff:
                        max_diff = diff
                    F[s] = best_f
                    policy[s] = best_action
            if max_diff < eps:
                break

        return F, policy

    def evaluate_policy(self, policy, max_iter=2000, eps=1e-10):
        """对固定策略，值迭代求单次尝试的 P 和 E（失败后不再重试，与 solve 一致）。"""
        states = self.enumerate_states()
        P = {s: 1.0 if s[0] >= self.target else 0.0 for s in states}
        E = {s: 0.0 if s[0] >= self.target else 0.0 for s in states}

        for _ in range(max_iter):
            max_diff = 0.0
            for s in states:
                pos = s[0]
                if pos >= self.target:
                    continue
                action = policy.get(s)
                if action is None:
                    continue
                cost = self.action_cost(action)
                success_state = self.cap_state(self.get_success_state(s, action))
                rate = self.immediate_success_rate(s, action)

                # 普通奔跑/助跑失败：游戏结束，P=0 E=0
                if action[0] in ('run', 'boost') and not (action[0] == 'run' and action[2]):
                    new_p = rate * P.get(success_state, 0.0)
                    new_e = cost + rate * E.get(success_state, 0.0)
                else:
                    # 防护失败：留在原地，继续本次尝试
                    fail_state = self.cap_state(self.get_failure_state(s, action))
                    new_p = rate * P.get(success_state, 0.0) + (1 - rate) * P.get(fail_state, 0.0)
                    new_e = cost + rate * E.get(success_state, 0.0) + (1 - rate) * E.get(fail_state, 0.0)

                max_diff = max(max_diff, abs(P[s] - new_p), abs(E[s] - new_e))
                P[s] = new_p
                E[s] = new_e
            if max_diff < eps:
                break

        start_state = (0, self.start_shield, self.start_boost, self.start_lucky)
        return P[start_state], E[start_state]

    def solve_reward_lambda(self, lam, max_iter=2000, eps=1e-10):
        """对给定 λ，用值迭代求 max H = R − λE（max_reward 模式子问题），返回 (H, policy)。"""
        states = self.enumerate_states()
        NEG = -1e6
        # 到达目标：R=0, E=0，所以 H=0
        H = {s: 0.0 if s[0] >= self.target else NEG for s in states}
        policy = {s: None for s in states}

        for _ in range(max_iter):
            max_diff = 0.0
            for s in states:
                pos = s[0]
                if pos >= self.target:
                    continue
                best_h = NEG
                best_action = None
                for action in self.get_actions(s):
                    cost = self.action_cost(action)
                    success_state = self.cap_state(self.get_success_state(s, action))
                    rate = self.immediate_success_rate(s, action)

                    if action[0] == 'run':
                        new_pos = min(pos + 10, self.target)
                    else:
                        new_pos = min(pos + 30, self.target)
                    reward_gain = self.reward_at(new_pos) - self.reward_at(pos)

                    if action[0] in ('run', 'boost') and not (action[0] == 'run' and action[2]):
                        # 普通奔跑/助跑失败：游戏结束，未来 H=0
                        h_val = rate * reward_gain - lam * cost + rate * H.get(success_state, NEG)
                    elif action[0] == 'run' and action[2]:
                        # 防护失败：留在原地继续
                        fail_state = self.cap_state(self.get_failure_state(s, action))
                        h_val = rate * reward_gain - lam * cost + rate * H.get(success_state, NEG) + (1 - rate) * H.get(fail_state, NEG)
                    else:
                        # 超级幸运 rate=1
                        h_val = reward_gain - lam * cost + H.get(success_state, NEG)

                    if h_val > best_h + 1e-12:
                        best_h = h_val
                        best_action = action
                if best_action is not None:
                    diff = abs(H[s] - best_h)
                    if diff > max_diff:
                        max_diff = diff
                    H[s] = best_h
                    policy[s] = best_action
            if max_diff < eps:
                break

        return H, policy

    def evaluate_policy_reward(self, policy, max_iter=2000, eps=1e-10):
        """对固定策略，值迭代求 R[start] 和 E[start]（max_reward 模式专用）。"""
        states = self.enumerate_states()
        R = {s: 0.0 for s in states}
        E = {s: 0.0 for s in states}

        for _ in range(max_iter):
            max_diff = 0.0
            for s in states:
                pos = s[0]
                if pos >= self.target:
                    continue
                action = policy.get(s)
                if action is None:
                    continue
                cost = self.action_cost(action)
                success_state = self.cap_state(self.get_success_state(s, action))
                rate = self.immediate_success_rate(s, action)

                if action[0] == 'run':
                    new_pos = min(pos + 10, self.target)
                else:
                    new_pos = min(pos + 30, self.target)
                reward_gain = self.reward_at(new_pos) - self.reward_at(pos)

                if action[0] in ('run', 'boost') and not (action[0] == 'run' and action[2]):
                    # 普通奔跑/助跑失败：游戏结束，未来 R=0, E=0
                    new_r = rate * (reward_gain + R.get(success_state, 0.0))
                    new_e = cost + rate * E.get(success_state, 0.0)
                elif action[0] == 'run' and action[2]:
                    # 防护失败：留在原地继续
                    fail_state = self.cap_state(self.get_failure_state(s, action))
                    new_r = rate * (reward_gain + R.get(success_state, 0.0)) + (1 - rate) * R.get(fail_state, 0.0)
                    new_e = cost + rate * E.get(success_state, 0.0) + (1 - rate) * E.get(fail_state, 0.0)
                else:
                    # 超级幸运 rate=1
                    new_r = reward_gain + R.get(success_state, 0.0)
                    new_e = cost + E.get(success_state, 0.0)

                max_diff = max(max_diff, abs(R[s] - new_r), abs(E[s] - new_e))
                R[s] = new_r
                E[s] = new_e
            if max_diff < eps:
                break

        start_state = (0, self.start_shield, self.start_boost, self.start_lucky)
        return R[start_state], E[start_state]

    def solve_min_ep(self, max_iter=50, eps=1e-9):
        """使用 Dinkelbach 算法最小化 E/P，返回 (P, E, policy)。"""
        lam = 0.0
        best_policy = None
        best_p, best_e = 0.0, float('inf')

        for _ in range(max_iter):
            F, policy = self.solve_lambda(lam)
            p, e = self.evaluate_policy(policy)
            if p <= 1e-12:
                break
            new_lam = e / p
            best_p, best_e = p, e
            best_policy = policy
            if abs(new_lam - lam) < eps:
                break
            lam = new_lam

        return best_p, best_e, best_policy

    def solve_max_reward_per_energy(self, max_iter=50, eps=1e-9):
        """使用 Dinkelbach 算法最大化 R/E，返回 (R, E, policy)。"""
        lam = 0.0
        best_policy = None
        best_r, best_e = 0.0, 0.0

        for _ in range(max_iter):
            H, policy = self.solve_reward_lambda(lam)
            r, e = self.evaluate_policy_reward(policy)
            if e <= 1e-12:
                break
            new_lam = r / e
            best_r, best_e = r, e
            best_policy = policy
            if abs(new_lam - lam) < eps:
                break
            lam = new_lam

        return best_r, best_e, best_policy

    def format_state(self, state):
        pos, shield, boost, lucky = state
        return f"{pos}m(防{shield} 助{boost} 幸{lucky})"

    def describe_action(self, state, action):
        pos, shield, boost, lucky = state
        if action[0] == 'run':
            _, q, use_shield = action
            rate = self.get_success_rate(pos)
            step = q - pos
            desc = f"从 {pos}m 普通奔跑至 {q}m（+{step}米，基础成功率 {rate*100:.1f}%）"
            if use_shield:
                final_rate = self.step_success_rate(state, action)
                desc += f"，使用 1 次防护（含失败后继续最优动作，本步最终成功率 {final_rate*100:.1f}%）"
            return desc
        elif action[0] == 'boost':
            rate = self.get_success_rate(pos - 10)
            new_pos = min(pos + 30, self.target)
            return f"从 {pos}m 使用助跑（退至 {pos-10}m，成功率 {rate*100:.1f}%），成功后到达 {new_pos}m"
        elif action[0] == 'lucky':
            new_pos = min(pos + 30, self.target)
            return f"从 {pos}m 使用超级幸运，到达 {new_pos}m"
        return str(action)

    def get_success_state(self, state, action):
        """根据动作返回成功后的下一个状态（用于打印成功路径）。"""
        pos, shield, boost, lucky = state
        if action[0] == 'run':
            _, q, use_shield = action
            used_shield = shield - 1 if use_shield else shield
            ns, nb = self.milestone_rewards(pos, q, used_shield, boost)
            nl = self.refill_lucky(pos, q, lucky)
            return (q, ns, nb, nl)
        elif action[0] == 'boost':
            back_pos = pos - 10
            new_pos = min(pos + 30, self.target)
            ns, nb = self.milestone_rewards(pos, new_pos, shield, boost - 1)
            nl = self.refill_lucky(pos, new_pos, lucky)
            return (new_pos, ns, nb, nl)
        elif action[0] == 'lucky':
            new_pos = min(pos + 30, self.target)
            ns, nb = self.milestone_rewards(pos, new_pos, shield, boost)
            nl = self.refill_lucky(pos, new_pos, lucky - 1)
            return (new_pos, ns, nb, nl)
        return state

    def step_success_rate(self, state, action):
        """计算该动作最终成功推进的成功概率。
        使用防护时，会递归考虑失败后 DP 推荐的最优动作（可继续防护/助跑/幸运等）。"""
        pos, shield, boost, lucky = state
        if action[0] == 'run':
            _, q, use_shield = action
            rate = self.get_success_rate(pos)
            if use_shield:
                if shield <= 0:
                    return rate
                fail_state = (pos, shield - 1, boost, lucky)
                fail_action = self.memo_action.get(fail_state)
                if fail_action is None:
                    return rate
                return rate + (1 - rate) * self.step_success_rate(fail_state, fail_action)
            return rate
        elif action[0] == 'boost':
            return self.get_success_rate(pos - 10)
        elif action[0] == 'lucky':
            return 1.0
        return 1.0

    def compute_success_path(self):
        """展开最优策略的成功路径，并返回 (path, final_state, cumulative_p)。"""
        start_state = (0, self.start_shield, self.start_boost, self.start_lucky)
        path = []
        state = start_state
        visited = set()
        while state[0] < self.target:
            if state in visited:
                break
            visited.add(state)
            action = self.memo_action.get(state)
            if action is None:
                break
            path.append((state, action))
            state = self.get_success_state(state, action)

        cumulative_p = 1.0
        i = 0
        while i < len(path):
            cur_state, action = path[i]
            if action[0] == 'run' and not action[2]:  # 无防护的普通奔跑合并
                combined_p = 1.0
                j = i
                while j < len(path) and path[j][1][0] == 'run' and not path[j][1][2]:
                    cur_state_j = path[j][0]
                    combined_p *= self.get_success_rate(cur_state_j[0])
                    j += 1
                cumulative_p *= combined_p
                i = j
            else:
                cumulative_p *= self.step_success_rate(cur_state, action)
                i += 1

        return path, state, cumulative_p

    def immediate_success_rate(self, state, action):
        """动作的即时成功率（不考虑失败后 fallback）。"""
        if action[0] == 'run':
            return self.get_success_rate(state[0])
        elif action[0] == 'boost':
            return self.get_success_rate(state[0] - 10)
        elif action[0] == 'lucky':
            return 1.0
        return 0.0

    def get_failure_state(self, state, action):
        """失败后进入的状态。"""
        pos, shield, boost, lucky = state
        if action[0] == 'run':
            _, q, use_shield = action
            if use_shield:
                # 防护失败：留在原地，消耗 1 次防护
                return (pos, shield - 1, boost, lucky)
            else:
                # 普通奔跑失败：游戏结束
                return None
        elif action[0] == 'boost':
            # 助跑失败：游戏结束
            return None
        elif action[0] == 'lucky':
            # 超级幸运不会失败
            return state
        return state

    def monte_carlo_simulate(self, n_simulations=100000):
        """蒙特卡洛模拟验证策略的正确性。
        返回 (empirical_p, empirical_e, empirical_e_given_success)。
        """
        import random
        successes = 0
        total_energy = 0.0
        success_energy = 0.0

        for _ in range(n_simulations):
            state = (0, self.start_shield, self.start_boost, self.start_lucky)
            energy = 0
            game_over = False

            while not game_over:
                pos = state[0]
                if pos >= self.target:
                    successes += 1
                    total_energy += energy
                    success_energy += energy
                    break

                action = self.memo_action.get(state)
                if action is None:
                    break

                rate = self.immediate_success_rate(state, action)
                cost = self.action_cost(action)
                energy += cost

                if random.random() < rate:
                    # 成功
                    state = self.cap_state(self.get_success_state(state, action))
                else:
                    # 失败
                    if action[0] == 'run' and action[2]:
                        # 防护奔跑失败：留在原地，shield-1
                        state = self.cap_state(self.get_failure_state(state, action))
                    else:
                        # 普通奔跑/助跑失败：游戏结束
                        total_energy += energy
                        game_over = True

        empirical_p = successes / n_simulations
        empirical_e = total_energy / n_simulations
        empirical_e_given_success = success_energy / successes if successes > 0 else float('inf')
        return empirical_p, empirical_e, empirical_e_given_success

    def evaluate_node_crossing_probabilities(self, policy, start_state, nodes=None):
        """对固定策略，对每个节点 n 值迭代求 V_n[start] = P(本局跨过 n)。"""
        if nodes is None:
            nodes = [100, 200, 300, 350, 450]
        states = self.enumerate_states()
        result = {}

        for n in nodes:
            V = {s: 0.0 for s in states}
            for _ in range(2000):
                max_diff = 0.0
                for state in states:
                    pos = state[0]
                    if pos >= self.target or pos >= n:
                        continue
                    action = policy.get(state)
                    if action is None:
                        continue
                    rate = self.immediate_success_rate(state, action)
                    success_state = self.cap_state(self.get_success_state(state, action))

                    if action[0] == 'run':
                        new_pos = min(pos + 10, self.target)
                    else:
                        new_pos = min(pos + 30, self.target)

                    if new_pos >= n:
                        if action[0] == 'run' and action[2]:
                            fail_state = self.cap_state(self.get_failure_state(state, action))
                            new_v = rate * 1.0 + (1 - rate) * V.get(fail_state, 0.0)
                        else:
                            new_v = rate * 1.0
                    else:
                        if action[0] == 'run' and action[2]:
                            fail_state = self.cap_state(self.get_failure_state(state, action))
                            new_v = rate * V.get(success_state, 0.0) + (1 - rate) * V.get(fail_state, 0.0)
                        else:
                            new_v = rate * V.get(success_state, 0.0)

                    max_diff = max(max_diff, abs(V[state] - new_v))
                    V[state] = new_v
                if max_diff < 1e-10:
                    break

            result[n] = V.get(start_state, 0.0)
        return result

    def monte_carlo_reward_simulate(self, energy_budget):
        """在能量预算内反复游戏，统计各装备件数、总奖励、实际消耗能量、总局数。"""
        import random
        counts = {100: 0, 200: 0, 300: 0, 350: 0, 450: 0}
        energy_used = 0
        games = 0
        total_reward = 0

        while energy_used < energy_budget:
            state = (0, self.start_shield, self.start_boost, self.start_lucky)
            game_over = False
            games += 1

            while not game_over and energy_used < energy_budget:
                pos = state[0]
                if pos >= self.target:
                    break

                action = self.memo_action.get(state)
                if action is None:
                    break

                rate = self.immediate_success_rate(state, action)
                cost = self.action_cost(action)

                if energy_used + cost > energy_budget:
                    game_over = True
                    break
                energy_used += cost

                if random.random() < rate:
                    old_pos = pos
                    state = self.cap_state(self.get_success_state(state, action))
                    new_pos = state[0]
                    for node in [100, 200, 300, 350, 450]:
                        if new_pos >= node and old_pos < node and self.reward_weights.get(node):
                            counts[node] += 1
                            total_reward += self.reward_weights[node]
                else:
                    if action[0] == 'run' and action[2]:
                        state = self.cap_state(self.get_failure_state(state, action))
                    else:
                        game_over = True

        return {'counts': counts, 'total_reward': total_reward, 'energy_used': energy_used, 'games': games}

    def print_policy_tree(self, state=None, prefix="", max_depth=5, visited=None):
        """打印从某状态出发的决策树（含成功/失败分支）。"""
        if state is None:
            state = (0, self.start_shield, self.start_boost, self.start_lucky)
        if visited is None:
            visited = set()

        if max_depth <= 0 or state[0] >= self.target:
            if state[0] >= self.target:
                print(f"到达 {self.format_state(state)}")
            else:
                print("...")
            return

        if state in visited:
            print(f"{self.format_state(state)} [已展开]")
            return
        visited.add(state)

        action = self.memo_action.get(state)
        if action is None:
            print(f"{self.format_state(state)} [无动作]")
            return

        rate = self.immediate_success_rate(state, action)
        print(f"{self.format_state(state)}: {self.describe_action(state, action)}")

        # 成功分支
        success_state = self.get_success_state(state, action)
        print(f"{prefix}  ├─ 成功 ({rate*100:.1f}%) → ", end="")
        self.print_policy_tree(success_state, prefix + "  │   ", max_depth - 1, visited)

        # 失败分支（返回起点的直接剪掉不显示）
        if action[0] == 'lucky':
            return
        fail_state = self.get_failure_state(state, action)
        if fail_state is None:
            # 普通奔跑/助跑失败 = 游戏结束，不展开
            return
        if fail_state == state:
            return
        if fail_state[0] == 0 and state[0] != 0:
            return
        print(f"{prefix}  └─ 失败 ({(1-rate)*100:.1f}%) → ", end="")
        self.print_policy_tree(fail_state, prefix + "      ", max_depth - 1, visited)

    def print_plan(self, objective='max_p'):
        start_state = (0, self.start_shield, self.start_boost, self.start_lucky)
        if objective == 'max_p':
            overall_p, e = self.solve(start_state)
            print(f"\n目标距离: {self.target}m")
            print(f"超级幸运等级: Lv.{self.level}（补充节点 {self.refill_point}m，最大次数 {self.max_lucky}）")
            print(f"优化目标: 最大化成功率")
            print(f"总体成功率 (DP 最优值): {overall_p*100:.4f}%")
            print(f"到达目标的期望能量饮料消耗: {e/overall_p:.2f} 个（含失败重试）")
        elif objective == 'max_reward':
            r, e, policy = self.solve_max_reward_per_energy()
            if policy is None or e <= 1e-12:
                print("未能找到可行策略（能量过低）。")
                return
            self.memo_action = policy
            # 单独求 P 用于显示
            overall_p, _ = self.evaluate_policy(policy)
            # 各节点跨越概率
            node_probs = self.evaluate_node_crossing_probabilities(policy, start_state)
            print(f"\n硬上限: {self.target}m（max_reward 模式固定为 450m）")
            print(f"超级幸运等级: Lv.{self.level}（补充节点 {self.refill_point}m，最大次数 {self.max_lucky}）")
            print(f"优化目标: 循环刷装备 (R/E)")
            print(f"奖励节点权重: {self.reward_weights}")
            print(f"总体成功率: {overall_p*100:.4f}%")
            print(f"期望总奖励 R: {r:.4f}")
            print(f"期望总能量 E: {e:.4f}")
            print(f"R/E 比 (DP 最优值): {r/e:.6f}")
            print(f"\n各节点跨越概率与预计件数（能量预算 100000）:")
            energy_budget = 100000
            for node in [100, 200, 300, 350, 450]:
                prob = node_probs.get(node, 0.0)
                forecast_count = energy_budget * prob / e if e > 1e-12 else 0
                print(f"  {node}m: 跨越概率 {prob*100:.4f}%, 预计件数 {forecast_count:.2f}")
            print(f"  预计局数: {energy_budget/e:.1f}")
        else:  # min_ep
            overall_p, e, policy = self.solve_min_ep()
            if policy is None or overall_p <= 1e-12:
                print("未能找到可行策略（成功率过低）。")
                return
            self.memo_action = policy
            print(f"\n目标距离: {self.target}m")
            print(f"超级幸运等级: Lv.{self.level}（补充节点 {self.refill_point}m，最大次数 {self.max_lucky}）")
            print(f"优化目标: 冲距离")
            print(f"总体成功率: {overall_p*100:.4f}%")
            print(f"到达目标的期望能量饮料消耗 (DP 最优值): {e/overall_p:.2f} 个（含失败重试）")

        path, final_state, _ = self.compute_success_path()

        print("\n最优方案决策树（成功 / 失败分支，返回起点的分支已隐藏）:")
        self.print_policy_tree(max_depth=6)

        print("\n最优方案（主成功路径摘要）:")
        step = 1
        i = 0
        while i < len(path):
            cur_state, action = path[i]
            if action[0] == 'run' and not action[2]:  # 无防护的普通奔跑
                start_pos = cur_state[0]
                end_pos = start_pos
                j = i
                while j < len(path) and path[j][1][0] == 'run' and not path[j][1][2]:
                    q = path[j][1][1]
                    end_pos = q
                    j += 1
                count = j - i
                if count == 1:
                    print(f"  步骤 {step} [{self.format_state(cur_state)}]: {self.describe_action(cur_state, action)}")
                else:
                    print(f"  步骤 {step} [{self.format_state(cur_state)}]: 从 {start_pos}m 连续普通奔跑至 {end_pos}m（{count} 步）")
                i = j
            else:
                print(f"  步骤 {step} [{self.format_state(cur_state)}]: {self.describe_action(cur_state, action)}")
                i += 1
            step += 1

        print(f"\n最终到达: {self.format_state(final_state)}")


def main():
    print("幸运冲刺最优策略求解器")
    print("=" * 50)

    try:
        current_level = int(input("\n当前超级幸运等级 (1-5): "))
        if current_level < 1 or current_level > 5:
            print("等级应在 1-5 之间")
            return

        print("\n优化目标选择:")
        print("  1: 冲距离")
        print("  2: 循环刷装备 (R/E，硬上限 450m)")
        obj_choice = input("请选择 (1-2): ").strip()

        if obj_choice == '2':
            objective = 'max_reward'
            target_distance = 450  # max_reward 模式固定为 450m 硬上限
            solver = LuckyRushSolver(current_level, target_distance)
        else:
            objective = 'min_ep'
            target_distance = int(input("目标距离 (米): "))
            if target_distance <= 0:
                print("目标距离应大于 0")
                return
            solver = LuckyRushSolver(current_level, target_distance)

        solver.print_plan(objective=objective)

    except ValueError as err:
        print(f"输入错误: {err}")
    except KeyboardInterrupt:
        print("\n已退出")


if __name__ == "__main__":
    main()
