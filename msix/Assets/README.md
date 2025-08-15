# MSIX Asset Requirements

This folder should contain the following PNG files required for MSIX packaging:

## Required images for MSIX package:
- StoreLogo.png (50x50)
- Square150x150Logo.png (150x150) 
- Square44x44Logo.png (44x44)
- Wide310x150Logo.png (310x150)
- SplashScreen.png (620x300)

## Notes:
- These are different from the main application icon (img/icon.ico)
- These images are used by Windows for Start Menu tiles, Store listings, etc.
- The GitHub Actions workflow will auto-generate these during build
- You can replace these with custom branded images for better appearance

## Design Guidelines:
- Use consistent branding across all sizes
- Ensure text/logos are readable at small sizes
- Follow Microsoft's MSIX asset guidelines

## Colors suggestion for Lemonade theme:
- Primary: #FFD700 (Gold/Yellow - like lemonade)
- Secondary: #FFA500 (Orange)  
- Background: #FFFFFF (White)
- Text: #333333 (Dark Gray)

## Tools:
- https://www.pwabuilder.com/imageGenerator for generating app icons
- GIMP or Photoshop for creating custom graphics
