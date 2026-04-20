/* global React, Navbar, Footer, Button, Bolt, Calendar, Clock, DevMobile, ChartBar, CheckSolid */

const Landing = ({ goApp }) => (
  <div className="bg-white">
    <Navbar onLogoClick={() => {}} showUser={false} />

    {/* Hero — the one custom gradient in the product */}
    <section
      className="text-white py-20"
      style={{ background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' }}
    >
      <div className="max-w-6xl mx-auto px-4 grid md:grid-cols-2 gap-12 items-center">
        <div>
          <h1 className="text-5xl font-bold leading-tight mb-4 text-white">
            ระบบนัดหมายออนไลน์<br />สำหรับผู้ให้บริการ
          </h1>
          <p className="text-lg text-white/90 mb-8 max-w-lg">
            จัดการนัดหมาย ลดเวลารอ เพิ่มประสิทธิภาพ — ระบบเดียวครบทุกฟังก์ชันสำหรับโรงพยาบาล คลินิก และศูนย์เฉพาะทาง
          </p>
          <div className="flex flex-wrap gap-4">
            <button onClick={goApp} className="bg-white text-purple-600 px-8 py-3 rounded-lg font-medium hover:bg-gray-100 transition-colors">
              ทดลองใช้ฟรี 14 วัน
            </button>
            <Button variant="outlineLight" size="xl">ขอสาธิตการใช้งาน</Button>
          </div>
          <p className="text-sm text-white/70 mt-6">ไม่ต้องใช้บัตรเครดิต · ยกเลิกได้ทุกเมื่อ</p>
        </div>
        <div className="hidden md:block">
          {/* Browser-style booking preview */}
          <div className="bg-white rounded-xl shadow-2xl p-1">
            <div className="flex items-center gap-1.5 px-3 py-2 border-b border-gray-100">
              <div className="w-2.5 h-2.5 rounded-full bg-red-400"></div>
              <div className="w-2.5 h-2.5 rounded-full bg-yellow-400"></div>
              <div className="w-2.5 h-2.5 rounded-full bg-green-400"></div>
              <div className="ml-3 text-[11px] text-gray-400 font-mono">humnoi.nuddee.com/book</div>
            </div>
            <div className="p-5 text-gray-900">
              <div className="text-sm font-semibold mb-2">เลือกเวลา — พุธ 15 ม.ค. 2568</div>
              <div className="grid grid-cols-4 gap-2">
                {['09:00','09:30','10:00','10:30','11:00','11:30','13:00','13:30'].map((t, i) => (
                  <div key={t} className={`text-center py-2 rounded-lg text-xs font-medium ${i === 2 ? 'bg-indigo-600 text-white' : 'border-2 border-gray-200 text-gray-900'}`}>{t}</div>
                ))}
              </div>
              <button className="mt-4 w-full py-2 rounded-lg bg-gradient-to-r from-purple-600 to-blue-600 text-white text-sm font-medium">ดำเนินการต่อ</button>
            </div>
          </div>
        </div>
      </div>
    </section>

    {/* Features */}
    <section className="py-20 bg-white">
      <div className="max-w-6xl mx-auto px-4">
        <div className="text-center mb-14">
          <h2 className="text-3xl font-bold text-gray-900 mb-3">ทำไมต้องเลือก NudDee?</h2>
          <p className="text-gray-600 text-lg">ระบบจัดการนัดหมายที่ออกแบบมาเพื่อผู้ให้บริการในประเทศไทย</p>
        </div>
        <div className="grid md:grid-cols-3 gap-8">
          <Feature icon={<Calendar className="w-6 h-6 text-purple-600" />} title="จัดตารางนัดง่าย" desc="ตั้งเวลาทำการ วันหยุด และประเภทการนัดหมายได้ในไม่กี่คลิก รองรับผู้ให้บริการหลายคน" />
          <Feature icon={<DevMobile className="w-6 h-6 text-purple-600" />} title="ผู้ป่วยจองเองได้ 24/7" desc="ส่งลิงก์ให้ผู้ป่วยจองเองผ่านมือถือ ไม่ต้องโทรเข้า ลดภาระเจ้าหน้าที่" />
          <Feature icon={<ChartBar className="w-6 h-6 text-purple-600" />} title="รายงานครบถ้วน" desc="ดูสถิติการจอง อัตรา no-show และรายงานรายเดือนแบบเรียลไทม์" />
        </div>
      </div>
    </section>

    {/* Pricing */}
    <section className="py-20 bg-gray-50">
      <div className="max-w-6xl mx-auto px-4">
        <div className="text-center mb-14">
          <h2 className="text-3xl font-bold text-gray-900 mb-3">แพ็คเกจที่เหมาะกับคุณ</h2>
          <p className="text-gray-600 text-lg">เริ่มต้นฟรี 14 วัน ไม่ต้องใช้บัตรเครดิต</p>
        </div>
        <div className="grid md:grid-cols-3 gap-8 max-w-5xl mx-auto">
          <Plan name="Basic" price="1,990" desc="คลินิกขนาดเล็ก 1–3 ห้องตรวจ" features={['ผู้ให้บริการ 20 คน','นัดหมาย 1,000 ครั้ง/เดือน','SMS แจ้งเตือน','รายงานพื้นฐาน']} />
          <Plan name="Professional" price="4,990" desc="ผู้ให้บริการขนาดกลาง" popular features={['ผู้ให้บริการ 100 คน','นัดหมายไม่จำกัด','Custom Domain','API Access','รายงานขั้นสูง']} />
          <Plan name="Enterprise" price="ติดต่อเรา" desc="โรงพยาบาลและเครือข่ายขนาดใหญ่" customPrice features={['ผู้ให้บริการไม่จำกัด','SLA 99.9%','Dedicated support','On-premise deploy']} />
        </div>
      </div>
    </section>

    <Footer />
  </div>
);

const Feature = ({ icon, title, desc }) => (
  <div className="text-center">
    <div className="w-12 h-12 bg-purple-100 rounded-xl flex items-center justify-center mx-auto mb-4">{icon}</div>
    <h3 className="text-xl font-semibold text-gray-900 mb-2">{title}</h3>
    <p className="text-gray-600">{desc}</p>
  </div>
);

const Plan = ({ name, price, desc, features, popular, customPrice }) => (
  <div className={`bg-white rounded-xl p-8 relative ${popular ? 'border-2 border-purple-600 shadow-xl' : 'shadow-md'}`}>
    {popular && (
      <div className="absolute -top-4 left-1/2 -translate-x-1/2 bg-purple-600 text-white text-xs font-semibold px-4 py-1 rounded-full">ยอดนิยม</div>
    )}
    <h3 className="text-xl font-bold text-gray-900 mb-1">{name}</h3>
    <p className="text-sm text-gray-500 mb-4">{desc}</p>
    <div className="mb-6">
      {customPrice ? (
        <div className="text-3xl font-bold text-gray-900">{price}</div>
      ) : (
        <div className="flex items-baseline gap-1">
          <span className="text-sm text-gray-500">฿</span>
          <span className="text-4xl font-bold text-gray-900">{price}</span>
          <span className="text-sm text-gray-500">/เดือน</span>
        </div>
      )}
    </div>
    <ul className="space-y-3 mb-8">
      {features.map((f) => (
        <li key={f} className="flex gap-2 text-sm text-gray-700 items-start">
          <CheckSolid className="w-5 h-5 text-green-500 flex-shrink-0 mt-0.5" />
          <span>{f}</span>
        </li>
      ))}
    </ul>
    <button className={`w-full py-2 rounded-lg font-medium text-sm transition-colors ${popular ? 'bg-purple-600 text-white hover:bg-purple-700' : 'border border-gray-300 text-gray-700 hover:bg-gray-50'}`}>
      {customPrice ? 'ติดต่อฝ่ายขาย' : 'เลือกแพ็คเกจนี้'}
    </button>
  </div>
);

Object.assign(window, { Landing });
