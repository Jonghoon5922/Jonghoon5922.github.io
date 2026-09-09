import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

// 글 — 프론트매터가 곧 상태 저장소다.
// project + until_commit 이 "지난 글 이후"를 계산하는 유일한 근거.
const posts = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/posts' }),
  schema: z.object({
    title: z.string(),
    date: z.coerce.date(),
    project: z.string(),
    tags: z.array(z.string()).default([]),
    until_commit: z.string().optional(),
    summary: z.string().optional(),
    draft: z.boolean().default(false),
  }),
});

// 프로젝트 — 각 프로젝트의 화면이 되는 자료
const projects = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/projects' }),
  schema: z.object({
    name: z.string(),
    order: z.number().default(99),
    summary: z.string(),
    repo: z.string().optional(),
    stack: z.array(z.string()).default([]),
    status: z.enum(['개발 중', '운영 중', '보류']).default('개발 중'),
  }),
});

export const collections = { posts, projects };
