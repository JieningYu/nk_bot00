from typing import Any
from collections import defaultdict

from mirai import Mirai
import httpx

import nk_bot00
import nk_bot00.util

URL_BASE = 'https://0xgame.h4ck.fun/api/v1'


class CTFGameStatus:
    def __init__(self, bot: Mirai, gosessid: str, target: list[str], week: str,
                 all_kill_category: bool, all_kill: bool, new_challenge: bool,
                 blood: bool, score_lower_than: int) -> None:
        self.bot = bot
        self.target = list(map(int, target))
        self.week = week
        self.all_kill_category = all_kill_category
        self.all_kill = all_kill
        self.new_challenge = new_challenge
        self.blood = blood
        self.score_lower_than = score_lower_than
        self.client = httpx.AsyncClient(headers={
            'User-Agent': f'nk_bot00/{nk_bot00.__version__}'
            f' (https://github.com/NKID00/nk_bot00)'
            f' httpx/{httpx.__version__}'
        }, cookies={'GOSESSID': gosessid})
        self.challenges: dict[int, Any] = {}
        '''{ChallengeId: Any, ...}'''
        self.previous_challenges: dict[int, Any] = {}
        '''{ChallengeId: Any, ...}'''
        self.categories: dict[str, set[int]] = defaultdict(set)
        '''{CategoryName: {ChallengeId, ...}, ...}'''
        self.users: dict[int, str] = {}
        '''{UserId: UserName, ...}'''
        self.solves: dict[int, set[int]] = defaultdict(set)
        '''{UserId: {ChallengeId, ...}, ...}'''
        self.previous_solves: dict[int, set[int]] = defaultdict(set)
        '''{UserId: {ChallengeId, ...}, ...}'''
        self.logger = nk_bot00.util.get_logger('ctf')

    async def call_api(self, api: str) -> Any:
        r = await self.client.get(URL_BASE + api)
        r.raise_for_status()
        data = r.json()
        if data['code'] != 200:
            raise httpx.HTTPStatusError(
                f'{data["code"]} {data["message"]}',
                request=r.request, response=r)
        return data['data']

    async def query(self) -> bool:
        self.challenges, self.previous_challenges = {}, self.challenges
        self.categories = defaultdict(set)
        self.users = {}
        self.solves, self.previous_solves = defaultdict(set), self.solves

        challenges = await self.call_api('/user/challenges/all')
        if challenges is None:
            self.logger.debug('No challenges')
            return False
        for challenge in challenges:
            cid = challenge['id']
            self.challenges[cid] = challenge
            self.categories[challenge['category']].add(cid)

        solves = await self.call_api('/user/solves/all')
        for solve in solves:
            self.users[solve['uid']] = solve['username']
            self.solves[solve['uid']].add(solve['cid'])

        self.logger.debug('C: %s, Cp: %s, U: %s, S: %s',
                          len(self.challenges), len(self.previous_challenges),
                          len(self.users), len(solves))
        return True

    async def check(self) -> None:
        if not await self.query():
            return
        for uid, solved in self.solves.items():
            previous_solved = self.previous_solves.get(uid, set())
            if solved == previous_solved:  # nothing is solved lately
                continue
            for cid in solved - previous_solved:
                if cid not in self.challenges:
                    continue
                challenge = self.challenges[cid]
                user_name = self.users[uid]
                challenge_name = challenge['name']
                solver_count = challenge['solver_count']
                self.logger.debug('%s, %s S %s, %s, %sP, %sS',
                                  user_name, uid, challenge_name,
                                  cid, challenge['score'],
                                  solver_count)
                if self.blood and solver_count <= 3:
                    await self.broadcast(
                        f'恭喜 {user_name} 拿下 {self.week} '
                        f'{challenge["category"]} '
                        f'{challenge_name} {"一二三"[solver_count - 1]}血！')
            for category, challenges in self.categories.items():
                if ((not challenges.issubset(previous_solved))  # already ak
                        and challenges.issubset(solved)
                        and self.all_kill_category):
                    await self.broadcast(
                        f'恭喜 {self.users[uid]} AK {self.week} {category}！')
            if set(self.challenges.keys()).issubset(solved) and self.all_kill:
                await self.broadcast(
                    f'恭喜 {self.users[uid]} AK {self.week}！')
        for cid, challenge in self.challenges.items():
            name = challenge['name']
            category = challenge['category']
            if cid not in self.previous_challenges and self.new_challenge:
                await self.broadcast(
                    f'{self.week} {category} 上了新题 {name}！')
                continue
            previous_challenge = self.previous_challenges[cid]
            score = challenge['score']
            previous_score = previous_challenge['score']
            if score < self.score_lower_than <= previous_score:
                await self.broadcast(
                    f'恭喜 {self.week} {category} {name} 被卷到'
                    f' {self.score_lower_than} 分以下！')

    async def broadcast(self, message: str) -> None:
        self.logger.debug('%s', message)
        for target in self.target:
            await self.bot.send_group_message(target, message)
