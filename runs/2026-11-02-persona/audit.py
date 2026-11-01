# Арифметика мандата-персоны: Елена Келлер + демографический фон.
# Числа — вывод этого скрипта; источники дат — PROVENANCE §2 (AFB, Britannica, PRB).
from datetime import date

born = date(1880, 6, 27)
died = date(1968, 6, 1)
days_life = (died - born).days

# зрячих/слышащих: 19 месяцев (примерно, месяц = 30.436875 сут)
days_sight = round(19 * 30.436875)
pct_sight = days_sight / days_life * 100

# "дно" (тьма+тишина без языка): болезнь ~ конец января 1882 -> приход учителя
illness = date(1882, 1, 27)   # 19 мес от 27.06.1880
arrivals = (date(1887, 3, 3), date(1887, 3, 5))
dark_days = [(a - illness).days for a in arrivals]

water = date(1887, 4, 5)
delta_teach_water = [(water - a).days for a in arrivals]

age_teacher_years = (date(1887, 3, 3) - born).days / 365.25
age_water_years = (water - born).days / 365.25

# демография PRB-2022
ever = 117e9
alive = 8e9
pct_alive = alive / ever * 100
pct_dead = 100 - pct_alive

# письменность ~3200 до н.э. vs сапиенс ~190000 до н.э. (PRB)
writing_years = 3200 + 2026
sapiens_years = 190000 + 2026
pct_writing = writing_years / sapiens_years * 100

print(f"Жила дней: {days_life}")
print(f"С глазами и ушами: {days_sight} сут = {pct_sight:.2f}% жизни")
print(f"Тьма+тишина (без языка): {dark_days[0]}-{dark_days[1]} сут = {dark_days[0]/365.25:.1f}-{dark_days[1]/365.25:.1f} лет")
print(f"Возраст к приходу учителя: {age_teacher_years:.2f} лет")
print(f"Возраст у помпы: {age_water_years:.2f} лет")
print(f"Учитель -> вода: {delta_teach_water[0]}-{delta_teach_water[1]} дней (в зависимости от версии даты)")
print(f"Живых сейчас: {pct_alive:.1f}% всех рождённых; мёртвых: {pct_dead:.1f}%")
print(f"Письменность = {writing_years} лет = {pct_writing:.2f}% времени сапиенса")
print(f"12 книг / {days_life/365.25:.0f} лет жизни: 1 книга на {days_life/12/365.25:.1f} лет")
