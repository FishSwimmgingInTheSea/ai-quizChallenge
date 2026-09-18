import { View } from '@tarojs/components'
import { mascotDataUri, MascotType } from './mascots'
import './index.scss'

interface MascotProps {
  type: MascotType
  /** 宽度，单位 px（设计稿像素，Taro 自动转 rpx） */
  size?: number
  className?: string
  floaty?: boolean
}

export default function Mascot({ type, size = 96, className = '', floaty = false }: MascotProps) {
  return (
    <View
      className={`mascot ${floaty ? 'floaty' : ''} ${className}`}
      style={{
        width: `${size}px`,
        height: `${(size * 195) / 180}px`,
        backgroundImage: `url("${mascotDataUri(type)}")`,
      }}
    />
  )
}
