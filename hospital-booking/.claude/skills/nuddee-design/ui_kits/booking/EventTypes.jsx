/* global React, Card, Clock, Calendar, CheckSolid */
const { useState: useStateET } = React;

const EVENT_TYPES = [
  { id: 'gp', name: 'ปรึกษาแพทย์ทั่วไป', desc: 'ตรวจร่างกาย ประเมินอาการ และวินิจฉัยโรคเบื้องต้น', duration: 30, advance: 30, color: '#6366f1' },
  { id: 'dent', name: 'ทำฟัน – ตรวจและทำความสะอาด', desc: 'ตรวจสุขภาพช่องปาก ขูดหินปูน และขัดฟัน', duration: 45, advance: 60, color: '#2563eb' },
  { id: 'skin', name: 'ผิวหนัง – ปรึกษาเฉพาะทาง', desc: 'ปรึกษาและวางแผนการรักษาโรคผิวหนังกับแพทย์เฉพาะทาง', duration: 30, advance: 45, color: '#9333ea' },
  { id: 'lab', name: 'ตรวจสุขภาพประจำปี', desc: 'แพคเกจตรวจสุขภาพครอบคลุม เจาะเลือด ตรวจปัสสาวะ X-ray', duration: 90, advance: 90, color: '#16a34a' },
];

const EventTypes = ({ onPick }) => {
  const [hoverId, setHoverId] = useStateET(null);
  return (
    <div className="min-h-screen" style={{ background: 'linear-gradient(to bottom right, #faf5ff, #eff6ff)' }}>
      <div className="max-w-6xl mx-auto px-4 py-12">
        <div className="mb-10 text-center">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">เลือกประเภทการนัดหมาย</h1>
          <p className="text-gray-600">โรงพยาบาลหำน้อย · humnoi.nuddee.com</p>
        </div>
        <div className="grid md:grid-cols-2 gap-6">
          {EVENT_TYPES.map((et) => (
            <button
              key={et.id}
              onMouseEnter={() => setHoverId(et.id)}
              onMouseLeave={() => setHoverId(null)}
              onClick={() => onPick(et)}
              className="text-left bg-white rounded-xl shadow-md hover:shadow-xl transition-all p-6"
              style={{ transform: hoverId === et.id ? 'translateY(-2px)' : 'none' }}
            >
              <div className="h-2 rounded-full mb-4" style={{ width: '40%', background: et.color }} />
              <h3 className="text-lg font-semibold text-gray-900 mb-2">{et.name}</h3>
              <p className="text-sm text-gray-600 mb-4 line-clamp-2">{et.desc}</p>
              <div className="flex items-center gap-5 text-sm text-gray-500 mb-5">
                <span className="inline-flex items-center gap-1.5"><Clock className="w-4 h-4" />{et.duration} นาที</span>
                <span className="inline-flex items-center gap-1.5"><Calendar className="w-4 h-4" />จองล่วงหน้าได้ {et.advance} วัน</span>
              </div>
              <div className="w-full py-2 rounded-lg bg-gradient-to-r from-purple-600 to-blue-600 text-white text-sm font-medium text-center">
                เลือกและดูเวลาว่าง
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};

Object.assign(window, { EventTypes, EVENT_TYPES });
