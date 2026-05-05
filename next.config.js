/** @type {import('next').NextConfig} */
const config = {
  eslint: {
    ignoreDuringBuilds: true,
    dirs: ['app', 'components', 'lib', 'data'],
  },
};

module.exports = config;
