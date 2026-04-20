/* global React, Stepper, Field, Input, Textarea, InfoCircle, Clock, Calendar, ChevLeft */
const { useState: useStateBF } = React;

const BookingForm = ({ eventType, pick, onSubmit, onBack }) => {
  const [form, setForm] = useStateBF({ name: '', email: '', phone: '', note: '' });
  const upd = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const label = `พุธ ${pick.date.d} ม.ค. ${pick.date.y + 543} · ${pick.time} น.`;

  return (
    <div className="min-h-screen" style={{ background: 'linear-gradient(to bottom right, #faf5ff, #eff6ff)' }}>
      <div className="max-w-6xl mx-auto px-4 py-10">
        <Stepper step={2} />

        <button onClick={onBack} className="inline-flex items-center gap-1.5 text-purple-600 hover:text-purple-700 text-sm font-medium mb-5">
          <ChevLeft className="w-4 h-4" /> กลับไปแก้ไขวันเวลา
        </button>

        <div className="grid lg:grid-cols-5 gap-6">
          {/* Form */}
          <form
            onSubmit={(e) => { e.preventDefault(); onSubmit(form); }}
            className="lg:col-span-3 bg-white rounded-xl shadow-md p-8 space-y-5"
          >
            <div>
              <h2 className="text-2xl font-bold text-gray-900 mb-1">ข้อมูลผู้จอง</h2>
              <p className="text-sm text-gray-500">กรุณากรอกข้อมูลเพื่อยืนยันการจอง</p>
            </div>

            <Field label="ชื่อ-นามสกุล" required>
              <Input required value={form.name} onChange={upd('name')} placeholder="เช่น สมชาย ใจดี" />
            </Field>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Field label="อีเมล" required help="ใช้สำหรับส่งการยืนยันและติดต่อกลับ">
                <Input type="email" required value={form.email} onChange={upd('email')} placeholder="example@email.com" />
              </Field>
              <Field label="เบอร์โทรศัพท์" optional="ถ้ามี" help="ขึ้นต้นด้วย 0 · 9–10 หลัก">
                <Input type="tel" value={form.phone} onChange={upd('phone')} placeholder="08x-xxx-xxxx" />
              </Field>
            </div>

            <Field label="หมายเหตุเพิ่มเติม" optional="ไม่บังคับ">
              <Textarea rows="3" value={form.note} onChange={upd('note')} placeholder="อาการเบื้องต้น หรือข้อมูลที่ต้องการแจ้งล่วงหน้า" />
            </Field>

            <div className="flex items-start gap-3 bg-blue-50 text-blue-800 rounded-lg p-4">
              <InfoCircle className="w-5 h-5 mt-0.5 flex-shrink-0 text-blue-600" />
              <p className="text-sm">หลังจากยืนยันการจอง คุณจะได้รับอีเมลยืนยันพร้อมรายละเอียดการนัดหมาย กรุณามาถึงก่อนเวลานัด 15 นาที</p>
            </div>

            <div className="flex items-center gap-2">
              <input id="terms" type="checkbox" defaultChecked className="h-4 w-4 text-purple-600 border-gray-300 rounded focus:ring-purple-500" style={{ accentColor: '#9333ea' }} />
              <label htmlFor="terms" className="text-sm text-gray-700">ยอมรับ<a className="text-purple-600 hover:underline cursor-pointer">เงื่อนไขการใช้งาน</a>และ<a className="text-purple-600 hover:underline cursor-pointer">นโยบายความเป็นส่วนตัว</a></label>
            </div>

            <button type="submit" className="w-full py-3 rounded-lg bg-gradient-to-r from-purple-600 to-blue-600 text-white font-medium hover:from-purple-700 hover:to-blue-700 transition-colors">
              ยืนยันการจอง
            </button>
          </form>

          {/* Sticky summary */}
          <aside className="lg:col-span-2">
            <div className="sticky top-20 bg-white rounded-xl shadow-md p-6">
              <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">สรุปการจอง</h3>
              <div className="space-y-3 border-b pb-4 mb-4">
                <div>
                  <div className="text-xs text-gray-500">ประเภทการนัดหมาย</div>
                  <div className="text-sm font-medium text-gray-900">{eventType.name}</div>
                </div>
                <div className="flex items-start gap-2">
                  <Calendar className="w-4 h-4 text-gray-400 mt-0.5" />
                  <div className="text-sm text-gray-700">{label}</div>
                </div>
                <div className="flex items-start gap-2">
                  <Clock className="w-4 h-4 text-gray-400 mt-0.5" />
                  <div className="text-sm text-gray-700">{eventType.duration} นาที</div>
                </div>
              </div>
              <div className="text-xs text-gray-500 space-y-1.5">
                <div className="flex justify-between"><span>โรงพยาบาลหำน้อย</span></div>
                <div>ชั้น 3 อาคาร A · 120 ถ.พญาไท</div>
                <div>02-123-4567</div>
              </div>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
};

Object.assign(window, { BookingForm });
