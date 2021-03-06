import datetime
from math import ceil
from decimal import Decimal, ROUND_HALF_UP
from dateutil.parser import parse

from ..fees import Common
from .monthly_storage import get_multiplier


class UnitedStates(Common):
    """United states fee calculations
    https://www.amazon.com/gp/aw/help/id=201119390
    """
    def __init__(self, year=2017):
        self._year = year
        self._fee_schedule = {
            "small_standard": {
                "non-media": 2.41,
                "media": 2.41
            },
            "large_standard": {
                "non-media": {
                    "a": 2.99,
                    "b": 4.18,
                    "c": lambda wt: (4.18 + max((wt - 2), 0) * 0.39)
                },
                "media": {
                    "a": 2.41,
                    "b": 2.99,
                    "c": lambda wt: (4.18 + max((wt - 2), 0) * 0.39)
                }
            },
            "small_oversize": lambda wt: (6.85 + max((wt - 2), 0) * 0.39),
            "medium_oversize": lambda wt: (9.20 + max((wt - 2), 0) * 0.39),
            "large_oversize": lambda wt: (75.06 + max((wt - 90), 0) * 0.80),
            "special_oversize": lambda wt: (138.08 + max((wt - 90), 0) * 0.92),
        }

    def _weight_class(self, wt):
        if(wt <= 1):
            return 'a'
        elif(wt > 1 and wt <= 2):
            return 'b'
        else:
            return 'c'

        return -1

    def get_order_handling(self, size, media):
        if size in ["small_standard", "large_standard"] and media is False:
            return 1
        else:
            return 0

    def get_pick_and_pack(self, size):
        matrix = [("std", 1.06), ("small", 4.09), ("medium", 5.20),
                  ("large", 8.40), ("special", 10.53)]

        if "standard" in size:
            size = "std"
        else:
            size = size.split('_', 1)[0]

        for item in matrix:
            if item[0] == size:
                return item[1]

    def get_weight_handling(self, tier, media, weight):
        matrix = {
            "small_standard": lambda x: 0.5 * x,
            "large_standard": {
                "media": lambda x: (
                    0.85 if x <= 1 else 1.24 + max((x - 2), 0) * 0.41),
                "non-media": lambda x: (
                    0.96 if x <= 1 else 1.95 + max((x - 2), 0) * 0.39)
                },
            "small_oversize": lambda x: (
                2.06 if x <= 2 else 2.06 + (x - 2) * 0.39),
            "medium_oversize": lambda x: (
                2.73 if x <= 2 else 2.73 + (x - 2) * 0.39),
            "large_oversize": lambda x: (
                63.98 if x <= 90 else 63.98 + (x - 90) * 0.80),
            "special_oversize": lambda x: (
                124.58 if x <= 90 else 124.58 + (x - 90) * 0.92),
             }

        prelim = matrix[tier]
        if isinstance(prelim, dict):
            prelim = prelim[media]

        return prelim(weight)

    def is_standard(self, l, w, h, wt):
        """Dims are in inches, weight in ounces.
        Hasn't changed for 2017.

        From Amazon:
        https://www.amazon.com/gp/help/customer/display.html?nodeId=201119390
        Any packaged item that is 20 lb. or less
        with its longest side 18" or less,
        and its median side 14" or less.
        its shortest side 8" or less,
        """

        # make sure all are floats
        values = list(map(lambda x: float(x), [l, w, h]))

        values.sort()

        return (values[0] <= 8 and values[1] <= 14
                and values[2] <= 18 and wt <= 20)

    def get_outbound_weight(self, volume, weight, oversize):
        """"Outbound Shipping Weight Calculation
        if package volume is greater than 5184, or if oversize,
        use dim weight if greater than unit weight
        """

        o_weight = weight
        if volume > 5184 or oversize:
            dim_weight = volume / 166
            if dim_weight > weight:
                o_weight = dim_weight

        return o_weight

    def get_product_size_tier(self, length, width, height, weight, media):
        """ Returns string describing product size tier """

        girth = 2 * (width + height) + length

        values = sorted([length, width, height], reverse=True)
        values = values + [girth, weight]

        tiers = [('15 12 .75 n/a .75', 'small_standard'),
                 ('18 14 8 n/a 20', 'large_standard'),
                 ('60 30 n/a 130 70', 'small_oversize'),
                 ('108 n/a n/a 130 150', 'medium_oversize'),
                 ('108 n/a n/a 165 150', 'large_oversize'),
                 ('9999999 n/a n/a 9999999 9999999', 'special_oversize')]

        if media:
            tiers = [('15 12 .75 n/a .875', 'small_standard')] + tiers

        def _compare(m):
            for pair in matrix:
                try:
                    spec = float(pair[1])
                except:
                    spec = None

                if spec is not None and pair[0] > spec:
                    return False

            return True

        for tier in tiers:
            specs = tier[0].split(' ')
            matrix = zip(values, specs)
            if _compare(matrix):
                return tier[1]

    def _determine_fee(self, tier, media, weight):
        if(tier == "small_standard"):
            return self._fee_schedule[tier][media]
        elif(tier == "large_standard"):
            wt_class = self._weight_class(weight)
            if(wt_class == 'a' or wt_class == 'b'):
                return self._fee_schedule[tier][media][wt_class]
            elif(wt_class == 'c'):
                return self._fee_schedule[tier][media][wt_class](weight)
        elif(tier == "small_oversize" or "special_oversize"):
            return self._fee_schedule[tier](weight)

        return 'undetermined fee'


    def get_fba_fee(self, amazon):
        requiredDims = ["shipping_weight", "shipping_width",
                        "shipping_height", "shipping_length"]

        category = amazon.__dict__.get('sales_rank_category', '')

        # Ensure we have needed dims
        for d in requiredDims:
            if d not in amazon.__dict__.keys():
                return False
            elif amazon.__dict__[d] is None:
                return False

        weight = amazon.shipping_weight
        width = amazon.shipping_width
        height = amazon.shipping_height
        length = amazon.shipping_length

        # weight is required to calculate the fee
        if weight is None:
            return False

        dim = [width, height, length]

        try:
            dim.sort(reverse=True)
        except TypeError:
            return False

        oversize = not self.is_standard(length, width, height, weight)
        volume = self.get_volume(length, width, height)
        o_weight = self.get_outbound_weight(volume, weight, oversize)

        media = self.is_media(category)
        size = self.get_product_size_tier(length, width, height,
                                          o_weight, media)

        sizes = ["small_oversize", "medium_oversize", "large_oversize"]

        # Redundant? isn't it part of outbound_weight?
        if size in sizes or (not media and weight > 1 and not oversize):
            weight = max(volume / 166, weight)

        if oversize:
            shipping_weight = weight + Decimal('1')
        else:
            shipping_weight = weight + Decimal('.25')

        shipping_weight = ceil(shipping_weight)

        mediaStr = "media" if media else "non-media"

        if(self._year == 2016):
            order_handling = self.get_order_handling(size, media)
            pick_and_pack = self.get_pick_and_pack(size)
            weight_handling = self.get_weight_handling(size, mediaStr,
                                                       shipping_weight)

            fee = order_handling + pick_and_pack + weight_handling
        elif(self._year == 2017):
            fee = self._determine_fee(size, mediaStr, shipping_weight)

        # clothing gets $0.40 additional pick and pack fee
        if category == 'Apparel':
            fee += 0.40

        return Decimal(fee).quantize(Decimal('.02'), rounding=ROUND_HALF_UP)

    def get_monthly_storage(self, date, l, w, h, wt):
        """Returns amazon storage fee for United States.

        This function is date agnostic.
        Multiplier is based on date passed in.
        """

        volume = self.get_volume(l, w, h)

        if volume is None:
            return None

        cubic_feet = volume / 1728
        size = self.is_standard(l, w, h, wt)

        # Find correct multiplier based on date, since fees change
        multiplier = get_multiplier(date)
        month = parse(date).month

        # Pass in month and size to the multiplier we were given
        res = Decimal(cubic_feet * multiplier(size, month))
        # print(volume, month)

        return res.quantize(Decimal('.02'), rounding=ROUND_HALF_UP)
