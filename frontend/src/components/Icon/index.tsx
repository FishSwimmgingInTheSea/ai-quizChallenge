import { View } from '@tarojs/components'
import { iconDataUri, IconName } from './icons'
import './index.scss'

interface IconProps {
  name: IconName
  /** 边长，单位 px（设计稿像素，Taro 自动转 rpx） */
  size?: number
  className?: string
}

export default function Icon({ name, size = 16, className = '' }: IconProps) {
  return (
    <View
      className={`icon ${className}`}
      style={{
        width: `${size}px`,
        height: `${size}px`,
        backgroundImage: `url("${iconDataUri(name)}")`,
      }}
    />
  )
}
