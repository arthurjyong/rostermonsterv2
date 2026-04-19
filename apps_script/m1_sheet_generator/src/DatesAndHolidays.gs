// DatesAndHolidays.gs
// Date-range expansion, weekend/holiday classification, and default call-point computation
// per the 4-case rule in docs/sheet_generation_contract.md section 8.
//
// All date arithmetic is done against UTC midnight to avoid DST and local-timezone drift.
// A YYYY-MM-DD string is treated as a pure calendar date.

// Local Singapore public-holiday map. Covers 2025 (gazetted) and 2026 (best-known at
// time of writing; includes Monday-in-lieu entries for Sunday holidays). Review 2026
// entries against the gazetted list before relying on them for a production roster.
var SG_PUBLIC_HOLIDAYS_SET_ = (function () {
  var list = [
    // 2025 (gazetted)
    '2025-01-01', // New Year's Day
    '2025-01-29', // Chinese New Year Day 1
    '2025-01-30', // Chinese New Year Day 2
    '2025-03-31', // Hari Raya Puasa
    '2025-04-18', // Good Friday
    '2025-05-01', // Labour Day
    '2025-05-12', // Vesak Day
    '2025-06-07', // Hari Raya Haji
    '2025-08-09', // National Day
    '2025-10-20', // Deepavali
    '2025-12-25', // Christmas Day

    // 2026 (best-known; verify against MOM gazette before production use)
    '2026-01-01', // New Year's Day
    '2026-02-17', // Chinese New Year Day 1
    '2026-02-18', // Chinese New Year Day 2
    '2026-03-20', // Hari Raya Puasa
    '2026-04-03', // Good Friday
    '2026-05-01', // Labour Day
    '2026-05-27', // Hari Raya Haji
    '2026-05-31', // Vesak Day
    '2026-06-01', // Vesak Day (observed, Monday in lieu)
    '2026-08-09', // National Day
    '2026-08-10', // National Day (observed, Monday in lieu)
    '2026-11-08', // Deepavali
    '2026-11-09', // Deepavali (observed, Monday in lieu)
    '2026-12-25', // Christmas Day
  ];
  var set = {};
  for (var i = 0; i < list.length; i++) set[list[i]] = true;
  return set;
})();

function parseYyyyMmDdToUtc_(isoString) {
  var m = String(isoString).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!m) throw new Error('Expected YYYY-MM-DD date, got: ' + JSON.stringify(isoString));
  var year = parseInt(m[1], 10);
  var month = parseInt(m[2], 10);
  var day = parseInt(m[3], 10);
  var d = new Date(Date.UTC(year, month - 1, day));
  if (d.getUTCFullYear() !== year || d.getUTCMonth() !== month - 1 || d.getUTCDate() !== day) {
    throw new Error('Invalid calendar date: ' + isoString);
  }
  return d;
}

function formatUtcAsIso_(date) {
  var y = date.getUTCFullYear();
  var m = date.getUTCMonth() + 1;
  var d = date.getUTCDate();
  return y + '-' + (m < 10 ? '0' + m : '' + m) + '-' + (d < 10 ? '0' + d : '' + d);
}

function addUtcDays_(date, n) {
  var out = new Date(date.getTime());
  out.setUTCDate(out.getUTCDate() + n);
  return out;
}

function getWeekdayShortLabel_(date) {
  return ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][date.getUTCDay()];
}

function isWeekend_(date) {
  var d = date.getUTCDay();
  return d === 0 || d === 6;
}

function isPublicHoliday_(date) {
  return SG_PUBLIC_HOLIDAYS_SET_[formatUtcAsIso_(date)] === true;
}

function isWeekendOrPublicHoliday_(date) {
  return isWeekend_(date) || isPublicHoliday_(date);
}

// Inclusive expansion of [startIso, endIso] into an ordered array of day descriptors.
function buildDateRange_(startIso, endIso) {
  var start = parseYyyyMmDdToUtc_(startIso);
  var end = parseYyyyMmDdToUtc_(endIso);
  if (start.getTime() > end.getTime()) {
    throw new Error('periodStartDate (' + startIso + ') must be on or before periodEndDate (' + endIso + ').');
  }
  var days = [];
  for (var d = new Date(start.getTime()); d.getTime() <= end.getTime(); d = addUtcDays_(d, 1)) {
    days.push({
      date: new Date(d.getTime()),
      isoDate: formatUtcAsIso_(d),
      weekdayLabel: getWeekdayShortLabel_(d),
      isWeekend: isWeekend_(d),
      isPublicHoliday: isPublicHoliday_(d),
      isWeph: isWeekendOrPublicHoliday_(d),
    });
  }
  return days;
}

// Default call-point for day N, using day N+1's classification for the transition.
// The 4-case matrix is taken directly from the point-row defaultRule declaration.
function computeDefaultCallPoint_(dayDate, defaultRule) {
  var nextDate = addUtcDays_(dayDate, 1);
  var nWeph = isWeekendOrPublicHoliday_(dayDate);
  var n1Weph = isWeekendOrPublicHoliday_(nextDate);
  if (!nWeph && !n1Weph) return defaultRule.weekdayToWeekday;
  if (!nWeph &&  n1Weph) return defaultRule.weekdayToWeekendOrPublicHoliday;
  if ( nWeph &&  n1Weph) return defaultRule.weekendOrPublicHolidayToWeekendOrPublicHoliday;
  return defaultRule.weekendOrPublicHolidayToWeekday;
}
