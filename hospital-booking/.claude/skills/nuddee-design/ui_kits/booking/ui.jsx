/* global React */
// Shared primitives — buttons, cards, inputs — matching NudDee Tailwind class vocabulary.

const Button = ({ variant = 'primary', size = 'md', children, className = '', ...rest }) => {
  const base = 'inline-flex items-center justify-center font-medium rounded-lg transition-colors cursor-pointer';
  const sizes = {
    sm: 'px-3 py-1.5 text-sm',
    md: 'px-4 py-2 text-sm',
    lg: 'px-6 py-2 text-base',
    xl: 'px-8 py-3 text-lg',
  };
  const variants = {
    primary: 'bg-purple-600 text-white hover:bg-purple-700',
    gradient: 'text-white bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700',
    secondary: 'border border-gray-300 text-gray-700 bg-white hover:bg-gray-50',
    ghost: 'text-purple-600 hover:text-purple-700 hover:underline',
    outlineLight: 'border-2 border-white text-white hover:bg-white hover:text-purple-600',
    disabled: 'bg-gray-300 text-white cursor-not-allowed',
  };
  return (
    <button className={`${base} ${sizes[size]} ${variants[variant]} ${className}`} {...rest}>
      {children}
    </button>
  );
};

const Card = ({ children, className = '', padding = 'p-6' }) => (
  <div className={`bg-white rounded-xl shadow-md ${padding} ${className}`}>{children}</div>
);

const Label = ({ children, required, optional }) => (
  <label className="block text-sm font-medium text-gray-700 mb-1">
    {children}
    {required && <span className="text-red-500"> *</span>}
    {optional && <span className="text-gray-400 font-normal"> ({optional})</span>}
  </label>
);

const Input = ({ className = '', ...rest }) => (
  <input
    className={`w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent ${className}`}
    {...rest}
  />
);

const Textarea = ({ className = '', ...rest }) => (
  <textarea
    className={`w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent ${className}`}
    {...rest}
  />
);

const Select = ({ children, className = '', ...rest }) => (
  <select
    className={`w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent bg-white ${className}`}
    {...rest}
  >
    {children}
  </select>
);

const Field = ({ label, required, optional, help, children }) => (
  <div>
    <Label required={required} optional={optional}>{label}</Label>
    {children}
    {help && <p className="text-xs text-gray-500 mt-1">{help}</p>}
  </div>
);

const Helper = ({ children }) => <p className="text-xs text-gray-500 mt-1">{children}</p>;

// Flash / alert banner used for celebration & error states
const Flash = ({ tone = 'success', children }) => {
  const tones = {
    success: 'bg-green-100 text-green-800 border-green-300',
    error: 'bg-red-100 text-red-800 border-red-300',
    info: 'bg-blue-100 text-blue-800 border-blue-300',
    warn: 'bg-yellow-100 text-yellow-800 border-yellow-300',
  };
  return <div className={`${tones[tone]} border rounded-lg px-4 py-3 text-sm`}>{children}</div>;
};

Object.assign(window, { Button, Card, Label, Input, Textarea, Select, Field, Helper, Flash });
