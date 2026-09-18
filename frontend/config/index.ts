import { defineConfig } from '@tarojs/cli'
import devConfig from './dev'
import prodConfig from './prod'

// 设计稿以 375pt 手机为基准（对齐 prototypes 原型宽度），1px -> 2rpx
export default defineConfig(async (merge, { command, mode }) => {
  const baseConfig = {
    projectName: 'zhiqu-ai-quiz',
    date: '2026-9-18',
    designWidth: 375,
    deviceRatio: {
      640: 2.34 / 2,
      750: 1,
      375: 2 / 1,
      828: 1.81 / 2,
    },
    sourceRoot: 'src',
    outputRoot: 'dist',
    plugins: [],
    // 微信小程序没有 Node 的 process；必须在编译期注入，否则 process.env.TARO_APP_API 会运行时报错
    defineConstants: {
      'process.env.TARO_APP_API': JSON.stringify(
        process.env.TARO_APP_API || 'http://127.0.0.1:8000/api/v1'
      ),
    },
    copy: {
      patterns: [],
      options: {},
    },
    framework: 'react',
    compiler: 'webpack5',
    cache: {
      enable: false,
    },
    mini: {
      postcss: {
        pxtransform: {
          enable: true,
          config: {},
        },
        cssModules: {
          enable: false,
        },
      },
    },
    h5: {
      publicPath: '/',
      staticDirectory: 'static',
      esnextModules: ['@tarojs'],
      postcss: {
        autoprefixer: {
          enable: true,
          config: {},
        },
        cssModules: {
          enable: false,
        },
      },
    },
  }

  if (mode === 'development') {
    return merge({}, baseConfig, devConfig)
  }
  return merge({}, baseConfig, prodConfig)
})
