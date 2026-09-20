export default defineAppConfig({
  pages: [
    'pages/index/index',
    'pages/login/index',
    'pages/generating/index',
    'pages/quiz/index',
    'pages/report/index',
    'pages/poster/index',
    'pages/profile/index',
    'pages/kb/index',
  ],
  window: {
    backgroundTextStyle: 'dark',
    navigationBarBackgroundColor: '#FBF9F5',
    navigationBarTitleText: '智趣 AI 闯关',
    navigationBarTextStyle: 'black',
    backgroundColor: '#F4F1EB',
  },
  tabBar: {
    color: '#A9A296',
    selectedColor: '#EA5A24',
    backgroundColor: '#FFFDF9',
    borderStyle: 'white',
    list: [
      {
        pagePath: 'pages/index/index',
        text: '闯关',
        iconPath: 'assets/tabbar/quiz.png',
        selectedIconPath: 'assets/tabbar/quiz-active.png',
      },
      {
        pagePath: 'pages/profile/index',
        text: '我的',
        iconPath: 'assets/tabbar/me.png',
        selectedIconPath: 'assets/tabbar/me-active.png',
      },
    ],
  },
})
