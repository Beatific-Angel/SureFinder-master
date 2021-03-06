import re

from surebet.parsing import *
from surebet.parsing.bets import *

TOTAL_INFO_KEYS = ['on', 'i', 'p', 'v']
HANDICAP_INFO_KEYS = ['on', 'p', 'v']

PART_BETS_ATTR = {
    'П1': 'o1',
    'П2': 'o2',
    'Х': 'ox',
    '1Х': 'o1x',
    '12': 'o12',
    'Х2': 'ox2',
}

HANDICAP_TYPES = ['Ф1', 'Ф2']

CORNERS_STR = 'Corners'


class Total:
    def __init__(self):
        self._type = self._id = ''
        self.cond = self.coef = self.factor_id = 0
        self.filled = False

    def add(self, _id, _type, cond, coef, factor_id):
        if not (len(_type) == 1 and _type in 'OU'):
            raise ParseException('Unknown total type "{}" '
                                 '(id: "{}", cond: "{}", coef: "{}").'.format(_type, _id, cond, coef))
        if not self.filled:
            self.fill(_id, _type, cond, coef, factor_id)
        else:
            if _id == self._id and _type != self._type and cond == self.cond:
                v1, v2 = self.coef, coef
                v1_id, v2_id = self.factor_id, factor_id
                if _type == 'O':
                    v1, v2 = v2, v1
                    v1_id, v2_id = v2_id, v1_id
                self.clear()
                return IdCondBet(cond, v1, v2, v1_id, v2_id)
            else:  # error
                self.fill(_id, _type, cond, coef, factor_id)

    def fill(self, _id, _type, cond, coef, factor_id):
        self._id = _id
        self._type = _type
        self.cond = cond
        self.coef = coef
        self.factor_id = factor_id
        self.filled = True

    def clear(self):
        self.__init__()


class TotalInfo:
    def __init__(self, bet):
        for key in TOTAL_INFO_KEYS:
            if key not in bet:
                raise StructureException('There is no key "{}" in bet: "{}".'.format(key, bet))
        self.id = bet['on']
        self.type = bet['i'][-1]
        self.cond = float(bet['p'])
        self.coef = float(bet['v'])
        self.team = 0
        team_char = bet['on'][-1]
        if team_char.isdigit():
            self.team = int(team_char)

        self.factor_id = bet["apid"]


class Handicap:
    def __init__(self):
        self.first_id = ''
        self.first_team = self.first_cond = self.first_coef = self.first_factor_id = 0
        self.filled = False

    def add(self, _id, team, cond, coef, factor_id):
        if not self.filled:
            self.fill(_id, team, cond, coef, factor_id)
        else:
            if _id == self.first_id and team != self.first_team and cond == -self.first_cond:
                if self.first_team == 1:
                    cond1, v1, v2 = self.first_cond, self.first_coef, coef
                    v1_id, v2_id = self.first_factor_id, factor_id
                else:
                    cond1, v1, v2 = cond, coef, self.first_coef
                    v1_id, v2_id = factor_id, self.first_factor_id
                self.clear()
                return IdCondBet(cond1, v1, v2, v1_id, v2_id)
            else:  # error
                self.fill(_id, team, cond, coef, factor_id)

    def fill(self, _id, team, cond, coef, factor_id):
        self.first_id = _id
        self.first_team = team
        self.first_cond = cond
        self.first_coef = coef
        self.first_factor_id = factor_id
        self.filled = True

    def clear(self):
        self.__init__()


class HandicapInfo:
    def __init__(self, bet):
        for key in HANDICAP_INFO_KEYS:
            if key not in bet:
                raise StructureException('There is no key "{}" in bet: "{}".'.format(key, bet))
        self.id = bet['on'][:-1]
        self.cond = float(bet['p'])
        self.coef = float(bet['v'])
        self.team = int(bet['on'][-1])

        self.factor_id = bet["apid"]


def is_valid_team_names(first_team, second_team):
    return first_team and second_team and not (CORNERS_STR in first_team and CORNERS_STR in second_team)


def parse(source, bookmaker):
    bookmaker_sports = {
        'soccer': bookmaker.soccer,
        'hockey': bookmaker.hockey,
        'basket': bookmaker.basket,
        'tennis': bookmaker.tennis,
        'volley': bookmaker.volley,
    }

    for sport_name, events in source.items():
        for event in events:
            first_team = event['c1']
            second_team = event['c2']
            if not is_valid_team_names(first_team, second_team):
                continue

            event_data = event['it']
            sport_id = event["sport_id"]

            parts = [parse_main_bets(event_data, sport_name)]
            parse_other_bets(event_data, sport_name, parts)  # quarter, period, set

            for part in parts:
                part.sport_id = sport_id

            bookmaker_sports[sport_name].append(Event(first_team, second_team, parts))

    return bookmaker


def parse_main_bets(event_data, sport_name):
    main_bets = OlimpPartBets()
    for bets_part in event_data:
        bets_part_name = bets_part['n']
        bets = bets_part['i']

        hand = Handicap()
        total = Total()

        if bets_part_name == 'Main Bets':
            for bet in bets:
                factor_id = bet["apid"]

                bet_type = bet['on']
                if bet_type in PART_BETS_ATTR:
                    set_exist_attr(main_bets, PART_BETS_ATTR[bet_type], IdBet(float(bet['v']), factor_id))
                elif bet_type in HANDICAP_TYPES:  # H1 and H2
                    add_handicap(bet, hand, main_bets)
                elif bet_type == 'Тот':  # Tot
                    add_total(bet, total, main_bets)
        elif bets_part_name == 'Individual total':  # only soccer
            if sport_name == 'soccer':
                for bet in bets:
                    add_ind_total(bet, total, main_bets)
        elif bets_part_name == 'Points':  # only basket (individual total)
            if sport_name == 'basket':
                for bet in bets:
                    add_ind_total(bet, total, main_bets)
        elif bets_part_name == 'Additional total':
            for bet in bets:
                add_total(bet, total, main_bets)
        elif bets_part_name == 'Additional handicap' or bets_part_name == 'Handicap':
            for bet in bets:
                add_handicap(bet, hand, main_bets)

    return main_bets


def parse_other_bets(event_data, sport_name, parts):
    # TODO Goals
    for bets_part in event_data:
        bets_part_name = bets_part['n']
        bets = bets_part['i']
        if not bets:  # for part number
            continue

        hand = Handicap()
        total = Total()

        if bets_part_name == 'Quarters outcome':  # basket
            # Ч3П1 Ч3Н Ч3П2 Ч3П1Ф0 Ч3П2Ф0 Ч3Ф1 Ч3Ф2 Ч3Тот
            for bet in bets:
                factor_id = bet["apid"]

                bet_type = bet['on']
                quarter_bets = get_part_bets(parts, get_part(bet_type, 'Ч'))
                coef = float(bet['v'])

                if bet_type[-1] == 'Н':
                    quarter_bets.ox = IdBet(coef, factor_id)
                elif bet_type[-2:] in PART_BETS_ATTR:  # П1 П2
                    set_exist_attr(quarter_bets, PART_BETS_ATTR[bet_type[-2:]], IdBet(coef, factor_id))
                elif bet_type[-2:] in HANDICAP_TYPES:
                    add_handicap(bet, hand, quarter_bets)
                elif bet_type[-3:] == 'Тот':
                    add_total(bet, total, quarter_bets)
        elif re.match(r'^[0-9] period: Periods outcome', bets_part_name):  # hockey
            # П3П1 П3Н П3П2 П31Х П312 П3Х2 П3Ф1 П3Ф2 П3Тот
            for bet in bets:
                factor_id = bet["apid"]

                bet_type = bet['on']
                period_bets = get_part_bets(parts, get_part(bet_type, 'П'))
                coef = float(bet['v'])

                if bet_type[-1] == 'Н':
                    period_bets.ox = IdBet(coef, factor_id)
                elif bet_type[-2:] in PART_BETS_ATTR:  # П1 П2
                    set_exist_attr(period_bets, PART_BETS_ATTR[bet_type[-2:]], IdBet(coef, factor_id))
                elif bet_type[-2:] in HANDICAP_TYPES:
                    add_handicap(bet, hand, period_bets)
                elif bet_type[-3:] == 'Тот':
                    add_total(bet, total, period_bets)
        elif re.match(r'^[0-9] period: Individual total', bets_part_name):  # hockey
            # П3К1 П3К2
            for bet in bets:
                period_bets = get_part_bets(parts, get_part(bet['on'], 'П'))
                add_ind_total(bet, total, period_bets)
        elif re.match(r'^[0-9] period: Additional total', bets_part_name):  # hockey
            # П3Тот2
            for bet in bets:
                period_bets = get_part_bets(parts, get_part(bet['on'], 'П'))
                add_total(bet, total, period_bets)
        elif bets_part_name == 'Bets by sets':  # tennis and volley
            if sport_name == 'tennis':
                for bet in bets:
                    factor_id = bet["apid"]

                    bet_type = bet['on']
                    set_bets = get_part_bets(parts, get_part(bet_type, 'С'))
                    bet_type_parts = bet_type.split('_')  # 'С2_Ф1_-2.5' => ['С2', 'Ф1', '-2.5']

                    if bet_type[-2:] in PART_BETS_ATTR:
                        set_exist_attr(set_bets, PART_BETS_ATTR[bet_type[-2:]], IdBet(float(bet['v']), factor_id))
                    elif 'Тот' in bet_type:  # total
                        add_total(bet, total, set_bets)
                    elif len(bet_type_parts) == 3 and ('Ф1' in bet_type or 'Ф2' in bet_type):  # handicap
                        cond_bet = hand.add(bet_type, int(bet_type_parts[1][1]),
                                            float(bet_type_parts[2]), float(bet['v']), factor_id)
                        if cond_bet:
                            set_bets.hand.append(cond_bet)
            elif sport_name == 'volley':
                # П1П2 П1Тот П1Тот2 П3Ф1 П3Ф2 д1П3Ф1 дП2Ф1
                for bet in bets:
                    factor_id = bet["apid"]

                    bet_type = bet['on']
                    set_bets = get_part_bets(parts, get_part(bet_type, 'П'))

                    if bet_type[-2:] in PART_BETS_ATTR:
                        set_exist_attr(set_bets, PART_BETS_ATTR[bet_type[-2:]], IdBet(float(bet['v']), factor_id))
                    elif 'Тот' in bet_type:  # total
                        add_total(bet, total, set_bets)
                    elif bet_type[-2:] in HANDICAP_TYPES:  # handicap
                        add_handicap(bet, hand, set_bets)
        elif bets_part_name == 'Halves betting':
            if sport_name == 'soccer':
                # Т1Тот2 Т2П1 Т1П2 Т1Н Т1Тот д1Т1Ф2 д1Т1Ф1 Т112 Т2Н Т1Ф2 Т1П1 Т2П2 Т1Х2 Т11Х Т1Ф1 Т1Тот3
                for bet in bets:
                    factor_id = bet["apid"]

                    bet_type = bet['on']
                    half_bets = get_part_bets(parts, get_part(bet_type, 'Т'))
                    coef = float(bet['v'])

                    if bet_type[-1] == 'Н':
                        half_bets.ox = IdBet(coef, factor_id)
                    elif bet_type[-2:] in PART_BETS_ATTR:
                        set_exist_attr(half_bets, PART_BETS_ATTR[bet_type[-2:]], IdBet(coef, factor_id))
                    elif bet_type[-2:] in HANDICAP_TYPES:
                        add_handicap(bet, hand, half_bets)
                    elif 'Тот' in bet_type:
                        add_total(bet, total, half_bets)


def get_part(bet_type, part_name_char):
    return int(bet_type[bet_type.index(part_name_char) + 1])  # ('д1П3Ф2', 'П') => 3


def get_part_bets(parts, part):
    for part_bets in parts:
        if part_bets.part == part:
            return part_bets
    part_bets = OlimpPartBets()
    part_bets.part = part
    parts.append(part_bets)
    return part_bets


def get_part_bets_attr(bet_type_str):
    if bet_type_str[-1] == 'Н' or len(bet_type_str) == 1 and bet_type_str[-1] == 'Х':
        return 'ox'

    two_last_chars = bet_type_str[-2:]
    if two_last_chars in PART_BETS_ATTR:
        return PART_BETS_ATTR[two_last_chars]

    if two_last_chars in HANDICAP_TYPES:
        return 'hand'

    if bet_type_str[-3:] == 'Тот':
        return 'total'


def add_handicap(bet, hand, part_bets):
    info = HandicapInfo(bet)
    cond_bet = hand.add(info.id, info.team, info.cond, info.coef, info.factor_id)
    if cond_bet:
        part_bets.hand.append(cond_bet)


def add_total(bet, total, part_bets):
    info = TotalInfo(bet)
    cond_bet = total.add(info.id, info.type, info.cond, info.coef, info.factor_id)
    if cond_bet:
        part_bets.total.append(cond_bet)


def add_ind_total(bet, total, part_bets):
    info = TotalInfo(bet)
    cond_bet = total.add(info.id, info.type, info.cond, info.coef, info.factor_id)
    if cond_bet:
        ind_total = part_bets.ind_total1 if info.team == 1 else part_bets.ind_total2
        ind_total.append(cond_bet)
