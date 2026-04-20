/* global React, ReactDOM, Landing, EventTypes, DateTimePicker, BookingForm, BookingSuccess, EVENT_TYPES */
const { useState, useEffect } = React;

const SCREENS = ['landing', 'events', 'datetime', 'form', 'success'];

const App = () => {
  // Persist state across reloads so iteration doesn't lose your place
  const [screen, setScreen] = useState(() => localStorage.getItem('nuddee_screen') || 'landing');
  const [eventType, setEventType] = useState(() => {
    try { return JSON.parse(localStorage.getItem('nuddee_et')) || EVENT_TYPES[0]; } catch { return EVENT_TYPES[0]; }
  });
  const [pick, setPick] = useState({ date: { d: 15, m: 0, y: 2025 }, time: '10:00' });
  const [customer, setCustomer] = useState({ name: 'สมชาย ใจดี', email: 'somchai@email.com', phone: '', note: '' });

  useEffect(() => { localStorage.setItem('nuddee_screen', screen); }, [screen]);
  useEffect(() => { localStorage.setItem('nuddee_et', JSON.stringify(eventType)); }, [eventType]);

  const jump = (s) => setScreen(s);

  let content;
  if (screen === 'landing') content = <Landing goApp={() => jump('events')} />;
  else if (screen === 'events') content = <EventTypes onPick={(et) => { setEventType(et); jump('datetime'); }} />;
  else if (screen === 'datetime') content = <DateTimePicker eventType={eventType} onBack={() => jump('events')} onNext={(p) => { setPick(p); jump('form'); }} />;
  else if (screen === 'form') content = <BookingForm eventType={eventType} pick={pick} onBack={() => jump('datetime')} onSubmit={(c) => { setCustomer(c); jump('success'); }} />;
  else if (screen === 'success') content = <BookingSuccess eventType={eventType} pick={pick} customer={customer} onRestart={() => jump('landing')} />;

  return (
    <div className="font-sans" data-screen-label={labelFor(screen)}>
      {content}
      <ScreenJumper current={screen} onJump={jump} />
    </div>
  );
};

const labelFor = (s) => ({
  landing: '01 Landing',
  events: '02 Event types',
  datetime: '03 Date & time',
  form: '04 Customer form',
  success: '05 Success',
}[s]);

// Small floating helper so we can step through the prototype without clicking through
const ScreenJumper = ({ current, onJump }) => {
  const [open, setOpen] = useState(true);
  return (
    <div className="fixed bottom-4 right-4 z-50">
      {open ? (
        <div className="bg-white rounded-xl shadow-lg border border-gray-200 p-3 min-w-[220px]">
          <div className="flex items-center justify-between mb-2">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">Prototype screens</div>
            <button onClick={() => setOpen(false)} className="text-gray-400 hover:text-gray-600 text-sm">×</button>
          </div>
          <div className="flex flex-col gap-1">
            {SCREENS.map((s) => (
              <button
                key={s}
                onClick={() => onJump(s)}
                className={`text-left text-xs px-2.5 py-1.5 rounded-md font-medium transition-colors ${current === s ? 'bg-purple-600 text-white' : 'text-gray-700 hover:bg-gray-100'}`}
              >{labelFor(s)}</button>
            ))}
          </div>
        </div>
      ) : (
        <button onClick={() => setOpen(true)} className="bg-purple-600 text-white rounded-full w-12 h-12 shadow-lg font-bold">☰</button>
      )}
    </div>
  );
};

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
