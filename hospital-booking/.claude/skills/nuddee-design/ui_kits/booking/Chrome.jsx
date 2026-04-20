/* global React, Bolt, ChevDown */

const Navbar = ({ onLogoClick, hospitalName = 'โรงพยาบาลหำน้อย', userName = 'นพ. สมชาย ใจดี', userInitial = 'ส', showUser = true }) => (
  <nav className="bg-white shadow-sm border-b sticky top-0 z-40">
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
      <div className="flex justify-between items-center h-16">
        <button onClick={onLogoClick} className="flex items-center gap-2 cursor-pointer">
          <Bolt className="w-8 h-8 text-purple-600" />
          <span className="text-xl font-bold text-gray-900">NudDee</span>
        </button>
        {showUser ? (
          <div className="flex items-center gap-4">
            <span className="text-sm text-gray-500 hidden sm:block">{hospitalName}</span>
            <div className="flex items-center gap-2 group cursor-pointer">
              <div className="w-8 h-8 rounded-full bg-purple-100 text-purple-600 flex items-center justify-center font-semibold text-sm">{userInitial}</div>
              <span className="text-sm font-medium text-gray-700 hidden sm:block">{userName}</span>
              <ChevDown className="w-4 h-4 text-gray-500" />
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-4">
            <a className="text-sm text-gray-600 hover:text-purple-600 cursor-pointer hidden sm:block">ราคา</a>
            <a className="text-sm text-gray-600 hover:text-purple-600 cursor-pointer hidden sm:block">คุณสมบัติ</a>
            <a className="text-sm text-gray-600 hover:text-purple-600 cursor-pointer">เข้าสู่ระบบ</a>
            <button className="bg-purple-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-purple-700 transition-colors">ทดลองใช้ฟรี</button>
          </div>
        )}
      </div>
    </div>
  </nav>
);

const Footer = () => (
  <footer className="bg-gray-900 text-gray-300 mt-16">
    <div className="max-w-7xl mx-auto px-4 py-12 grid grid-cols-2 md:grid-cols-4 gap-8 text-sm">
      <div className="col-span-2">
        <div className="flex items-center gap-2 mb-3">
          <Bolt className="w-8 h-8 text-purple-400" />
          <span className="text-xl font-bold text-white">NudDee</span>
        </div>
        <p className="text-gray-400 max-w-xs">ระบบจัดการนัดหมายออนไลน์สำหรับโรงพยาบาล คลินิก และศูนย์เฉพาะทางในประเทศไทย</p>
      </div>
      <div>
        <h4 className="text-white font-semibold mb-3">ผลิตภัณฑ์</h4>
        <ul className="space-y-2">
          <li><a className="hover:text-white cursor-pointer">คุณสมบัติ</a></li>
          <li><a className="hover:text-white cursor-pointer">ราคา</a></li>
          <li><a className="hover:text-white cursor-pointer">API</a></li>
        </ul>
      </div>
      <div>
        <h4 className="text-white font-semibold mb-3">ติดต่อ</h4>
        <ul className="space-y-2">
          <li>02-123-4567</li>
          <li>hello@nuddee.com</li>
          <li>กรุงเทพฯ ประเทศไทย</li>
        </ul>
      </div>
    </div>
    <div className="border-t border-gray-800 py-6 text-center text-xs text-gray-500">
      © 2568 NudDee. สงวนลิขสิทธิ์ทุกประการ
    </div>
  </footer>
);

Object.assign(window, { Navbar, Footer });
