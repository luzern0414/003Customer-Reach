"""用于身份比较的行政名称键；不改写来源事实或补全未知地区。"""


def city_key(value: str | None) -> str:
    """value为原文城市，可空；仅去掉三个字以上名称末尾的市，空值返回空，不做行政区推断。"""
    city=(value or '').strip()
    return city[:-1] if len(city)>2 and city.endswith('市') else city


def city_values(value: str | None) -> list[str]:
    """value为原文城市，可空；返回SQL精确比较用的市后缀等价值，空值仅匹配空字符串。"""
    key=city_key(value)
    return list(dict.fromkeys([value or '',key,*([key+'市'] if len(key)>=2 and not key.endswith('市') else [])]))
