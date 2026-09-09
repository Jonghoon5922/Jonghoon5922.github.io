// @ts-check
import { defineConfig } from 'astro/config';

// site 는 저장소 이름이 정해지면 확정한다.
// 사용자 사이트(Jonghoon5922.github.io)면 base 불필요, 프로젝트 사이트(blog)면 base: '/blog' 추가.
export default defineConfig({
  site: 'https://jonghoon5922.github.io',
});
