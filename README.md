# MSW 5 Thunder Stamper

這是一個用於生成MSW造型水印的工具，支援自訂png圖片或英數字碼並套用到圖片上。

---

## 使用方式

### 方案一：直接執行 EXE
1. 解壓縮下載的壓縮包。
2. 執行 `MSW 5 Thunder Stamper.exe`。
3. 第一次啟動會自動建立一個 `glyphs` 資料夾。
4. 將自製的字元 PNG（a~z, A~Z, 0~9）放進 `glyphs` 資料夾。
5. 程式會使用這些素材生成水印。

### 方案二：使用 Python 原始碼
1. 安裝 Python 3.10+。
2. 安裝必要套件：
   ```bash
   pip install pillow PySide6
   ```
3. 執行：
   ```bash
   python "MSW 5 Thunder Stamper v1.0.0.py"
   ```

---

## 檔案結構
```
MSW 5 Thunder Stamper.exe    # 可執行檔
MSW 5 Thunder Stamper v1.0.0.py # 原始碼
glyphs/                     # 字元素材（a~z, A~Z, 0~9 PNG）
origin.png                  # 預設紅點圖
README.md                   # 本說明文件
```

---

## 注意事項
- `glyphs` 資料夾一定要存在（就算是空的，程式會自動建立）。
- 字元 PNG 素材需自行準備，放入 `glyphs` 資料夾。
- 預設紅點圖檔名為 `origin.png`。

---

## 授權 | License

MIT License

Copyright (c) 2025 DuoDuo

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

作者：**DuoDuo**  
發布：**2025**
