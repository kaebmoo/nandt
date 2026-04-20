/* global React, Button, Flash, Calendar, Clock, InfoCircle */

const BookingSuccess = ({ eventType, pick, customer, onRestart }) => {
  const ref = 'NDD-' + Math.random().toString(36).slice(2, 8).toUpperCase();
  const label = `พุธ ${pick.date.d} ม.ค. ${pick.date.y + 543} · ${pick.time} น.`;
  return (
    <div className="min-h-screen" style={{ background: 'linear-gradient(to bottom right, #f0fdf4, #eff6ff)' }}>
      <div className="max-w-2xl mx-auto px-4 py-16">
        <Flash tone="success"><span className="mr-1">🎉</span>สร้างการจองสำเร็จ! ระบบได้ส่งอีเมลยืนยันไปยัง <b>{customer.email || 'somchai@email.com'}</b> แล้ว</Flash>

        <div className="mt-6 bg-white rounded-xl shadow-lg p-8 text-center">
          <div className="mx-auto mb-6 flex items-center justify-center w-20 h-20 rounded-full bg-green-100">
            <svg className="w-10 h-10 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <h1 className="text-3xl font-bold text-gray-900 mb-2">จองนัดหมายสำเร็จ!</h1>
          <p className="text-gray-600 mb-6">ขอบคุณที่เลือกใช้บริการกับเรา</p>

          <div className="text-left bg-gray-50 rounded-xl p-6 mb-6 space-y-3">
            <Row label="รหัสการจอง" value={<span className="font-mono text-purple-600 font-semibold">{ref}</span>} />
            <Row label="ประเภท" value={eventType.name} />
            <Row label="วันเวลา" value={<span className="inline-flex items-center gap-1.5"><Calendar className="w-4 h-4 text-gray-400" />{label}</span>} />
            <Row label="ระยะเวลา" value={<span className="inline-flex items-center gap-1.5"><Clock className="w-4 h-4 text-gray-400" />{eventType.duration} นาที</span>} />
            <Row label="ผู้จอง" value={customer.name || '—'} />
            <Row label="สถานที่" value={'โรงพยาบาลหำน้อย · ชั้น 3 อาคาร A'} />
          </div>

          <div className="flex items-start gap-3 text-left bg-blue-50 text-blue-800 rounded-lg p-4 mb-6">
            <InfoCircle className="w-5 h-5 mt-0.5 flex-shrink-0 text-blue-600" />
            <p className="text-sm">กรุณามาถึงก่อนเวลานัด 15 นาที และนำบัตรประชาชนมาด้วย หากต้องการยกเลิกหรือเลื่อนนัด กรุณาแจ้งล่วงหน้าอย่างน้อย 24 ชั่วโมง</p>
          </div>

          <div className="flex gap-3 justify-center">
            <button className="inline-flex items-center gap-2 px-6 py-2.5 rounded-lg bg-gradient-to-r from-purple-600 to-blue-600 text-white font-medium text-sm">
              <Calendar className="w-4 h-4" /> เพิ่มลงในปฏิทิน
            </button>
            <button onClick={onRestart} className="px-6 py-2.5 rounded-lg border border-gray-300 text-gray-700 bg-white font-medium text-sm hover:bg-gray-50">
              กลับหน้าหลัก
            </button>
          </div>
        </div>

        <p className="text-xs text-gray-500 text-center mt-6">มีคำถาม? โทร 02-123-4567 หรือ hello@nuddee.com</p>
      </div>
    </div>
  );
};

const Row = ({ label, value }) => (
  <div className="flex justify-between items-start gap-3">
    <span className="text-sm text-gray-500">{label}</span>
    <span className="text-sm font-medium text-gray-900 text-right">{value}</span>
  </div>
);

Object.assign(window, { BookingSuccess });
