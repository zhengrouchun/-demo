# 顾时夜 Q 版桌宠素材

更新日期：2026-10-03（Asia/Shanghai）。本批次按用户提供的六姿势参考图重新生成，仅替换七张同名 PNG。工具为内置 imagegen，transparent_background=true；未使用 CLI、API Key 或项目中的 AI 接口。

素材目录：`app/frontend/public/pet/gushiye/`。七张图片均为 1254 × 1254 的 RGBA PNG，已检查实际透明通道与一致的画布尺寸。原有状态、台词、设置、触发条件和布局代码没有修改。

参考图：`C:/Users/Stu15/AppData/Local/Temp/codex-clipboard-29caedaa-683f-4536-ae71-089d5853cc65.png`，用途为角色外观、画风和动作参考。先生成 idle，其余动作同时参考用户图与新 idle，以保持同一人物设计。

角色采用参考图中的蓬松深色侧分短发、棕灰色大眼睛、柔和肤色与腮红、深色毛领长外套、白衬衫、藏蓝领带、金色纽扣和链饰。idle 双手插袋，blink 为闭眼，touch 抓衣襟，wave 招手，surprise 惊讶，drag 为斜向悬空动作，sleep 为蜷坐趴膝。生成式素材不等同于逐像素复制参考图。

旧的七张正式素材备份目录：`D:/语音转文字工具/LocalLecture/data/pet-asset-backups/reference-20261003-095615`。生成原文件仍保留在 Codex 生成目录。

## 本次完整提示词

每次调用均输出一张独立图片。idle 输入用户参考图；另外六张输入用户参考图与新 idle。以下为各次调用的实际提示词。

### idle.png

```text
Use case: stylized-concept. Asset type: ONE transparent PNG chibi web-pet sprite.
Input image 1 is the user's character reference sheet, not an output layout. Closely preserve that EXACT character identity and illustration style; render only ONE character for the requested state, never the six-panel sheet.
Character: an exceptionally cute male chibi, about 2.3 heads tall, oversized rounded head, short voluminous tousled charcoal-black hair swept sideways with long soft fringe and warm cream hair highlights; big sparkling warm taupe-brown eyes, soft peach skin, faint pink cheeks, tiny nose and mouth.
EXACT reference outfit: charcoal-black tailored long coat with a thick dark-brown fluffy fur collar, white shirt collar, dark navy-blue tie, matching black buttoned waistcoat with small gold buttons and a fine gold pocket-watch chain draped on the chest; matching black trousers and black shoes. Preserve the fur collar, tie, gold chain, head shape and hairstyle throughout.
Style: same polished hand-painted anime chibi as the reference, fine dark linework, soft warm detailed shading, rounded adorable proportions. No realistic adult or 3D toy.
Composition: square canvas, full body fully visible, ONE centered character, consistent standing head size occupying about 46% of canvas height; standing hair top at about 7% and shoe soles at about 93%. Enough transparent margins for hands/hair/coat. The entire canvas background MUST be actual alpha transparency, including around the silhouette; the apparent black in the reference is NOT a black backdrop to reproduce. No rectangle, floor, shadow backdrop, border, speech bubble, labels, watermark, or text. Natural dark outline only, no sticker white outline.

State: IDLE. Re-create the top-left reference pose faithfully: relaxed full-body standing, both hands tucked in the coat pockets, gentle closed-mouth tiny smile, large open taupe-brown eyes. No decorative symbols. Keep the fluffy fur collar and navy tie distinctly visible.
```

### blink.png

```text
Use case: stylized-concept. Asset type: ONE transparent PNG chibi web-pet sprite.
Input image 1 is the user's character reference sheet, not an output layout. Closely preserve that EXACT character identity and illustration style; render only ONE character for the requested state, never the six-panel sheet.
Character: an exceptionally cute male chibi, about 2.3 heads tall, oversized rounded head, short voluminous tousled charcoal-black hair swept sideways with long soft fringe and warm cream hair highlights; big sparkling warm taupe-brown eyes, soft peach skin, faint pink cheeks, tiny nose and mouth.
EXACT reference outfit: charcoal-black tailored long coat with a thick dark-brown fluffy fur collar, white shirt collar, dark navy-blue tie, matching black buttoned waistcoat with small gold buttons and a fine gold pocket-watch chain draped on the chest; matching black trousers and black shoes. Preserve the fur collar, tie, gold chain, head shape and hairstyle throughout.
Style: same polished hand-painted anime chibi as the reference, fine dark linework, soft warm detailed shading, rounded adorable proportions. No realistic adult or 3D toy.
Composition: square canvas, full body fully visible, ONE centered character, consistent standing head size occupying about 46% of canvas height; standing hair top at about 7% and shoe soles at about 93%. Enough transparent margins for hands/hair/coat. The entire canvas background MUST be actual alpha transparency, including around the silhouette; the apparent black in the reference is NOT a black backdrop to reproduce. No rectangle, floor, shadow backdrop, border, speech bubble, labels, watermark, or text. Natural dark outline only, no sticker white outline.

Input image 2 is the newly generated IDLE sprite: keep precisely its character design, outfit, rendering style and scale. Image 1 provides the desired expression and action reference.
State: BLINK. Same neutral standing pose as the new idle image, both hands remain in the coat pockets. Change ONLY both eyes to gently closed eyelids, a quiet blink, tiny closed-mouth smile. Preserve the exact head position, size, hair silhouette, clothes and feet placement from image 2. No symbols.
```

### touch.png

```text
Use case: stylized-concept. Asset type: ONE transparent PNG chibi web-pet sprite.
Input image 1 is the user's character reference sheet, not an output layout. Closely preserve that EXACT character identity and illustration style; render only ONE character for the requested state, never the six-panel sheet.
Character: an exceptionally cute male chibi, about 2.3 heads tall, oversized rounded head, short voluminous tousled charcoal-black hair swept sideways with long soft fringe and warm cream hair highlights; big sparkling warm taupe-brown eyes, soft peach skin, faint pink cheeks, tiny nose and mouth.
EXACT reference outfit: charcoal-black tailored long coat with a thick dark-brown fluffy fur collar, white shirt collar, dark navy-blue tie, matching black buttoned waistcoat with small gold buttons and a fine gold pocket-watch chain draped on the chest; matching black trousers and black shoes. Preserve the fur collar, tie, gold chain, head shape and hairstyle throughout.
Style: same polished hand-painted anime chibi as the reference, fine dark linework, soft warm detailed shading, rounded adorable proportions. No realistic adult or 3D toy.
Composition: square canvas, full body fully visible, ONE centered character, consistent standing head size occupying about 46% of canvas height; standing hair top at about 7% and shoe soles at about 93%. Enough transparent margins for hands/hair/coat. The entire canvas background MUST be actual alpha transparency, including around the silhouette; the apparent black in the reference is NOT a black backdrop to reproduce. No rectangle, floor, shadow backdrop, border, speech bubble, labels, watermark, or text. Natural dark outline only, no sticker white outline.

Input image 2 is the newly generated IDLE sprite: keep precisely its character design, outfit, rendering style and scale. Image 1 provides the desired expression and action reference.
State: TOUCH. Closely match the TOP-RIGHT pose on the user's reference sheet: standing in place, both tiny hands gently holding the coat lapels near the tie, warm cheek blush, round wide taupe-brown eyes and a tiny o-shaped mouth reacting to a gentle tap. Head subtly tilts. No decorative symbols. Maintain the new idle sprite's exact outfit and head size.
```

### wave.png

```text
Use case: stylized-concept. Asset type: ONE transparent PNG chibi web-pet sprite.
Input image 1 is the user's character reference sheet, not an output layout. Closely preserve that EXACT character identity and illustration style; render only ONE character for the requested state, never the six-panel sheet.
Character: an exceptionally cute male chibi, about 2.3 heads tall, oversized rounded head, short voluminous tousled charcoal-black hair swept sideways with long soft fringe and warm cream hair highlights; big sparkling warm taupe-brown eyes, soft peach skin, faint pink cheeks, tiny nose and mouth.
EXACT reference outfit: charcoal-black tailored long coat with a thick dark-brown fluffy fur collar, white shirt collar, dark navy-blue tie, matching black buttoned waistcoat with small gold buttons and a fine gold pocket-watch chain draped on the chest; matching black trousers and black shoes. Preserve the fur collar, tie, gold chain, head shape and hairstyle throughout.
Style: same polished hand-painted anime chibi as the reference, fine dark linework, soft warm detailed shading, rounded adorable proportions. No realistic adult or 3D toy.
Composition: square canvas, full body fully visible, ONE centered character, consistent standing head size occupying about 46% of canvas height; standing hair top at about 7% and shoe soles at about 93%. Enough transparent margins for hands/hair/coat. The entire canvas background MUST be actual alpha transparency, including around the silhouette; the apparent black in the reference is NOT a black backdrop to reproduce. No rectangle, floor, shadow backdrop, border, speech bubble, labels, watermark, or text. Natural dark outline only, no sticker white outline.

Input image 2 is the newly generated IDLE sprite: keep precisely its character design, outfit, rendering style and scale. Image 1 provides the desired expression and action reference.
State: WAVE. Closely match the TOP-MIDDLE pose on the user's reference sheet: happy open-mouth smile, ONE hand raised above shoulder with open palm toward viewer in greeting, other arm relaxed beside body, coat hem softly lifted. Keep large warm taupe-brown eyes. Maintain the new idle sprite's exact outfit and head size. One character only, no symbols.
```

### surprise.png

```text
Use case: stylized-concept. Asset type: ONE transparent PNG chibi web-pet sprite.
Input image 1 is the user's character reference sheet, not an output layout. Closely preserve that EXACT character identity and illustration style; render only ONE character for the requested state, never the six-panel sheet.
Character: an exceptionally cute male chibi, about 2.3 heads tall, oversized rounded head, short voluminous tousled charcoal-black hair swept sideways with long soft fringe and warm cream hair highlights; big sparkling warm taupe-brown eyes, soft peach skin, faint pink cheeks, tiny nose and mouth.
EXACT reference outfit: charcoal-black tailored long coat with a thick dark-brown fluffy fur collar, white shirt collar, dark navy-blue tie, matching black buttoned waistcoat with small gold buttons and a fine gold pocket-watch chain draped on the chest; matching black trousers and black shoes. Preserve the fur collar, tie, gold chain, head shape and hairstyle throughout.
Style: same polished hand-painted anime chibi as the reference, fine dark linework, soft warm detailed shading, rounded adorable proportions. No realistic adult or 3D toy.
Composition: square canvas, full body fully visible, ONE centered character, consistent standing head size occupying about 46% of canvas height; standing hair top at about 7% and shoe soles at about 93%. Enough transparent margins for hands/hair/coat. The entire canvas background MUST be actual alpha transparency, including around the silhouette; the apparent black in the reference is NOT a black backdrop to reproduce. No rectangle, floor, shadow backdrop, border, speech bubble, labels, watermark, or text. Natural dark outline only, no sticker white outline.

Input image 2 is the newly generated IDLE sprite: keep precisely its character design, outfit, rendering style and scale. Image 1 provides the desired expression and action reference.
State: SURPRISE. Closely match the BOTTOM-RIGHT pose on the user's reference sheet: full-body standing, both hands raised near chest, open palms and fingers spread, eyebrows raised, sparkling wide taupe-brown eyes and round open mouth. Small golden comic surprise star beside hair and two small blue sweat droplets as in the reference, not words. Preserve the new idle character's exact head size, hairstyle and outfit.
```

### drag.png

```text
Use case: stylized-concept. Asset type: ONE transparent PNG chibi web-pet sprite.
Input image 1 is the user's character reference sheet, not an output layout. Closely preserve that EXACT character identity and illustration style; render only ONE character for the requested state, never the six-panel sheet.
Character: an exceptionally cute male chibi, about 2.3 heads tall, oversized rounded head, short voluminous tousled charcoal-black hair swept sideways with long soft fringe and warm cream hair highlights; big sparkling warm taupe-brown eyes, soft peach skin, faint pink cheeks, tiny nose and mouth.
EXACT reference outfit: charcoal-black tailored long coat with a thick dark-brown fluffy fur collar, white shirt collar, dark navy-blue tie, matching black buttoned waistcoat with small gold buttons and a fine gold pocket-watch chain draped on the chest; matching black trousers and black shoes. Preserve the fur collar, tie, gold chain, head shape and hairstyle throughout.
Style: same polished hand-painted anime chibi as the reference, fine dark linework, soft warm detailed shading, rounded adorable proportions. No realistic adult or 3D toy.
Composition: square canvas, full body fully visible, ONE centered character, consistent standing head size occupying about 46% of canvas height; standing hair top at about 7% and shoe soles at about 93%. Enough transparent margins for hands/hair/coat. The entire canvas background MUST be actual alpha transparency, including around the silhouette; the apparent black in the reference is NOT a black backdrop to reproduce. No rectangle, floor, shadow backdrop, border, speech bubble, labels, watermark, or text. Natural dark outline only, no sticker white outline.

Input image 2 is the newly generated IDLE sprite: keep precisely its character design, outfit, rendering style and scale. Image 1 provides the desired expression and action reference.
State: DRAG. Closely match the BOTTOM-LEFT pose on the user's reference sheet: chibi is playfully carried in the air, body tilted diagonally with head toward upper-left and feet lower-right, both hands reaching forward, coat tails sweep backward to right, legs loosely bent, slightly flustered cute open-mouth expression and blue sweat droplets. Preserve the new idle character's exact identity, head size, fur collar, navy tie, gold chain and black outfit. Everything including hands, shoes and coat fully within the square transparent canvas. Do not add a cursor or a person carrying him.
```

### sleep.png

```text
Use case: stylized-concept. Asset type: ONE transparent PNG chibi web-pet sprite.
Input image 1 is the user's character reference sheet, not an output layout. Closely preserve that EXACT character identity and illustration style; render only ONE character for the requested state, never the six-panel sheet.
Character: an exceptionally cute male chibi, about 2.3 heads tall, oversized rounded head, short voluminous tousled charcoal-black hair swept sideways with long soft fringe and warm cream hair highlights; big sparkling warm taupe-brown eyes, soft peach skin, faint pink cheeks, tiny nose and mouth.
EXACT reference outfit: charcoal-black tailored long coat with a thick dark-brown fluffy fur collar, white shirt collar, dark navy-blue tie, matching black buttoned waistcoat with small gold buttons and a fine gold pocket-watch chain draped on the chest; matching black trousers and black shoes. Preserve the fur collar, tie, gold chain, head shape and hairstyle throughout.
Style: same polished hand-painted anime chibi as the reference, fine dark linework, soft warm detailed shading, rounded adorable proportions. No realistic adult or 3D toy.
Composition: square canvas, full body fully visible, ONE centered character, consistent standing head size occupying about 46% of canvas height; standing hair top at about 7% and shoe soles at about 93%. Enough transparent margins for hands/hair/coat. The entire canvas background MUST be actual alpha transparency, including around the silhouette; the apparent black in the reference is NOT a black backdrop to reproduce. No rectangle, floor, shadow backdrop, border, speech bubble, labels, watermark, or text. Natural dark outline only, no sticker white outline.

Input image 2 is the newly generated IDLE sprite: keep precisely its character design, outfit, rendering style and scale. Image 1 provides the desired expression and action reference.
State: SLEEP. Closely match the BOTTOM-MIDDLE pose on the user's reference sheet: sits curled up on the invisible ground, knees drawn up, arms folded atop knees, sleepy oversized head tipped onto crossed arms, both eyes fully closed, coat softly pooled around his feet. Keep the same actual head size as the new standing idle sprite, don't enlarge to fill the shorter seated pose. Shoes and coat bottom near the same lower margin as idle. Preserve exactly the reference's hair, thick dark-brown fur collar, white collar, navy tie, gold buttons and watch chain. No bed, pillow, letters or text. One cute sleeping character on true transparent alpha.
```

## 替换与刷新

保持同名 PNG 并重新运行 `npm.cmd run build`（工作目录 `app/frontend`）。现有服务可继续运行；浏览器使用 Ctrl+F5 刷新以加载新图片。

WALK 素材与开关仍按原配置预留。本次不改人物大小、定位、对白、动作概率或功能逻辑。
