/* global React, ChevLeft, ChevRight */
const { useState: useStateDT } = React;

// Stepper
const Stepper = ({ step }) => {
  const items = [
    { n: 1, label: 'เลือกวันเวลา' },
    { n: 2, label: 'กรอกข้อมูล' },
    { n: 3, label: 'ยืนยันการจอง' },
  ];
  return (
    <div className="flex items-center max-w-2xl mx-auto mb-8">
      {items.map((it, i) => {
        const done = step > it.n;
        const active = step === it.n;
        return (
          <React.Fragment key={it.n}>
            <div className="flex items-center">
              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold ${done ? 'bg-green-600 text-white' : active ? 'bg-purple-600 text-white' : 'bg-gray-300 text-white'}`}>
                {done ? (
                  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M16.7 5.3a1 1 0 010 1.4l-8 8a1 1 0 01-1.4 0l-4-4a1 1 0 011.4-1.4L8 12.6l7.3-7.3a1 1 0 011.4 0z" clipRule="evenodd" /></svg>
                ) : it.n}
              </div>
              <span className={`ml-2 text-sm font-medium ${done ? 'text-green-700' : active ? 'text-purple-600' : 'text-gray-400'} hidden sm:inline`}>{it.label}</span>
            </div>
            {i < items.length - 1 && (
              <div className="flex-1 h-1 mx-3 rounded-full" style={{ background: done ? '#16a34a' : active ? '#9333ea' : '#e5e7eb' }} />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
};

// Calendar grid for a given month
const THAI_DOW = ['อา','จ','อ','พ','พฤ','ศ','ส'];
const THAI_MONTHS = ['มกราคม','กุมภาพันธ์','มีนาคม','เมษายน','พฤษภาคม','มิถุนายน','กรกฎาคม','สิงหาคม','กันยายน','ตุลาคม','พฤศจิกายน','ธันวาคม'];

const CalGrid = ({ year, month, selected, today, onPick }) => {
  const firstDow = new Date(year, month, 1).getDay();
  const daysIn = new Date(year, month + 1, 0).getDate();
  const cells = [];
  for (let i = 0; i < firstDow; i++) cells.push(null);
  for (let d = 1; d <= daysIn; d++) cells.push(d);

  return (
    <div>
      <div className="grid grid-cols-7 gap-1.5 mb-2 px-1">
        {THAI_DOW.map((d, i) => (
          <div key={d+i} className={`text-center text-xs font-medium py-1 ${i === 0 ? 'text-red-500' : 'text-gray-600'}`}>{d}</div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-1.5">
        {cells.map((d, i) => {
          if (d === null) return <div key={i} />;
          const dow = i % 7;
          const isPast = d < today.d && year <= today.y && month <= today.m;
          const isToday = d === today.d && month === today.m && year === today.y;
          const isSel = d === selected.d && month === selected.m && year === selected.y;
          const isHoliday = (d === 1 || d === 22) && month === today.m; // sample
          const base = 'relative rounded-lg text-center py-2.5 text-sm font-medium cursor-pointer transition-colors';
          let cls = 'bg-gray-100 hover:bg-indigo-100 text-gray-900';
          if (isSel) cls = 'bg-indigo-600 text-white hover:bg-indigo-700';
          else if (isHoliday) cls = 'bg-red-100 text-rose-700 cursor-not-allowed';
          else if (isPast) cls = 'text-gray-300 bg-transparent cursor-not-allowed';
          if (isToday && !isSel) cls += ' ring-2 ring-indigo-600 ring-inset';
          return (
            <div key={i} className={`${base} ${cls}`} onClick={() => !isPast && !isHoliday && onPick(d)}>
              {d}
              {isHoliday && <div className="text-[9px] leading-none mt-0.5">ปิด</div>}
            </div>
          );
        })}
      </div>
    </div>
  );
};

const TIMES = ['09:00','09:30','10:00','10:30','11:00','11:30','13:00','13:30','14:00','14:30','15:00','15:30'];
const DISABLED_TIMES = new Set(['11:30','15:00']);

const DateTimePicker = ({ eventType, onNext, onBack }) => {
  const [year, setYear] = useStateDT(2025);
  const [month, setMonth] = useStateDT(0); // January
  const today = { d: 10, m: 0, y: 2025 };
  const [selected, setSelected] = useStateDT({ d: 15, m: 0, y: 2025 });
  const [time, setTime] = useStateDT('10:00');

  const monthLabel = `${THAI_MONTHS[month]} ${year + 543}`;
  const dayLabel = `พุธ ${selected.d} ม.ค. ${selected.y + 543}`;

  const prev = () => month === 0 ? (setMonth(11), setYear(year - 1)) : setMonth(month - 1);
  const next = () => month === 11 ? (setMonth(0), setYear(year + 1)) : setMonth(month + 1);

  return (
    <div className="min-h-screen" style={{ background: 'linear-gradient(to bottom right, #faf5ff, #eff6ff)' }}>
      <div className="max-w-6xl mx-auto px-4 py-10">
        <Stepper step={1} />

        <div className="mb-6">
          <button onClick={onBack} className="inline-flex items-center gap-1.5 text-purple-600 hover:text-purple-700 text-sm font-medium">
            <ChevLeft className="w-4 h-4" /> กลับไปเลือกประเภท
          </button>
          <h1 className="text-2xl font-bold text-gray-900 mt-3">{eventType.name}</h1>
          <p className="text-sm text-gray-600">{eventType.duration} นาที · โรงพยาบาลหำน้อย</p>
        </div>

        <div className="grid lg:grid-cols-5 gap-6">
          {/* Calendar */}
          <div className="lg:col-span-3 bg-white rounded-xl shadow-md p-6">
            <div className="flex items-center justify-between mb-4">
              <button onClick={prev} className="p-2 rounded-lg hover:bg-gray-100 text-gray-600"><ChevLeft className="w-5 h-5" /></button>
              <h3 className="text-lg font-semibold text-gray-900">{monthLabel}</h3>
              <button onClick={next} className="p-2 rounded-lg hover:bg-gray-100 text-gray-600"><ChevRight className="w-5 h-5" /></button>
            </div>
            <CalGrid year={year} month={month} selected={selected} today={today} onPick={(d) => setSelected({ d, m: month, y: year })} />
            <div className="flex gap-3 mt-5 flex-wrap text-xs text-gray-500">
              <Legend sw="bg-gray-100" label="ว่าง" />
              <Legend sw="bg-indigo-600" label="เลือก" />
              <Legend sw="ring-2 ring-indigo-600 ring-inset bg-white" label="วันนี้" />
              <Legend sw="bg-red-100" label="วันหยุด" />
            </div>
          </div>

          {/* Time slots */}
          <div className="lg:col-span-2 bg-white rounded-xl shadow-md p-6">
            <div className="bg-purple-50 text-purple-700 font-medium px-4 py-2 rounded-lg text-sm mb-4">{dayLabel}</div>
            <div className="grid grid-cols-3 gap-2 mb-5">
              {TIMES.map((t) => {
                const disabled = DISABLED_TIMES.has(t);
                const sel = t === time;
                return (
                  <button
                    key={t}
                    disabled={disabled}
                    onClick={() => setTime(t)}
                    className={`py-2 rounded-lg text-sm font-medium border-2 transition-colors ${sel ? 'bg-indigo-600 text-white border-indigo-600' : disabled ? 'bg-gray-100 text-gray-400 border-gray-100 line-through cursor-not-allowed' : 'bg-white text-gray-900 border-gray-200 hover:border-purple-400'}`}
                  >{t}</button>
                );
              })}
            </div>
            <button
              onClick={() => onNext({ date: selected, time })}
              className="w-full py-3 rounded-lg bg-gradient-to-r from-purple-600 to-blue-600 text-white font-medium hover:from-purple-700 hover:to-blue-700 transition-colors"
            >ดำเนินการต่อ</button>
            <p className="text-xs text-gray-500 text-center mt-3">ช่วงเวลาตามเวลาประเทศไทย (UTC+7)</p>
          </div>
        </div>
      </div>
    </div>
  );
};

const Legend = ({ sw, label }) => (
  <span className="inline-flex items-center gap-1.5"><span className={`w-3 h-3 rounded ${sw}`} />{label}</span>
);

Object.assign(window, { DateTimePicker, Stepper });
