"""Pre-defined knowledge base templates for easy bot creation"""

TEMPLATES = {
    'none': {
        'name': 'Bosh shablon',
        'icon': 'bi-plus-circle-dotted',
        'description': 'Botni o\'zingiz noldan o\'rgatasiz',
        'entries': []
    },
    'restaurant': {
        'name': 'Restoran / Kafe',
        'icon': 'bi-shop',
        'description': 'Menyu, manzillar, yetkazib berish va rezervatsiya',
        'entries': [
            {'type': 'qa', 'source': 'Asosiy', 'content': 'Savol: Ish vaqtingiz qanday?\nJavob: Biz har kuni soat 10:00 dan 23:00 gacha xizmat ko\'rsatamiz.'},
            {'type': 'qa', 'source': 'Asosiy', 'content': 'Savol: Yetkazib berish (dostavka) bormi?\nJavob: Ha, shahar bo\'ylab yetkazib berish mavjud. Tariftlar manzilingizga qarab belgilanadi (o\'rtacha 15,000 - 25,000 so\'m).'},
            {'type': 'qa', 'source': 'Asosiy', 'content': 'Savol: Stol band qilish (rezerv) mumkinmi?\nJavob: Ha, stol band qilish uchun menejerimizga "+998" harflari bilan boshlanuvchi raqamingizni qoldiring, biz albatta aloqaga chiqamiz.'},
            {'type': 'product', 'source': 'Maxsus Burger', 'content': 'Mahsulot: Maxsus Burger\nNarx: 35000\nTavsif: Mol go\'shti, pishloq, maxsus sous va yangi sabzavotlar qo\'shilgan katta burger.\nRasm: https://images.unsplash.com/photo-1568901346375-23c9450c58cd?q=80&w=600&auto=format&fit=crop'},
            {'type': 'product', 'source': 'Pepperoni Pitsa', 'content': 'Mahsulot: Pepperoni Pitsa (O\'rtacha)\nNarx: 65000\nTavsif: Italiyancha xamir, mazzali pepperoni kolbasasi va Mozzarella pishlog\'i.\nRasm: https://images.unsplash.com/photo-1628840042765-356cda07504e?q=80&w=600&auto=format&fit=crop'}
        ]
    },
    'clinic': {
        'name': 'Klinika / Shifokor',
        'icon': 'bi-hospital',
        'description': 'Qabulga yozilish, xizmatlar, narxlar va maslahat',
        'entries': [
            {'type': 'qa', 'source': 'Asosiy', 'content': 'Savol: Klinika manzili qayerda?\nJavob: Bizning manzilimiz: Toshkent shahar, Yunusobod tumani, 19-dahasi. Mo\'ljal: Mega Planet.'},
            {'type': 'qa', 'source': 'Asosiy', 'content': 'Savol: Qabulga qanday yozilsam bo\'ladi?\nJavob: Qabulga yozilish uchun Ism-familiyangiz va telefon raqamingizni qoldiring. Operatorimiz sizga mos vaqtni belgilash uchun aloqaga chiqadi.'},
            {'type': 'qa', 'source': 'Asosiy', 'content': 'Savol: Qanaqa shifokorlar bor?\nJavob: Bizda tajribali Terapevt, Kardiolog, Nevropatolog, Lor va Stomatolog bo\'limlari faoliyat yuritadi.'},
            {'type': 'product', 'source': 'Stomatolog konsultatsiyasi', 'content': 'Mahsulot: Stomatolog konsultatsiyasi\nNarx: 50000\nTavsif: Tishlarni to\'liq tekshirish va muolaja rejasini tuzib berish xizmati.\nRasm: https://images.unsplash.com/photo-1606811841689-23dfddce3e95?q=80&w=600&auto=format&fit=crop'},
            {'type': 'product', 'source': 'Kardiolog qabuli', 'content': 'Mahsulot: Kardiolog qabuli + EKG\nNarx: 120000\nTavsif: Tajribali kardiolog xulosasi va yurak kardiogrammasi.\nRasm: https://images.unsplash.com/photo-1579684385127-1ef15d508118?q=80&w=600&auto=format&fit=crop'}
        ]
    },
    'clothing': {
        'name': 'Kiyim-kechak Do\'koni',
        'icon': 'bi-bag-heart',
        'description': 'Modellar, o\'lchamlar, chegirmalar',
        'entries': [
            {'type': 'qa', 'source': 'Asosiy', 'content': 'Savol: O\'lchamlar (razmerlar) qanday?\nJavob: Bizda barcha kiyimlar uchun S, M, L, XL va XXL o\'lchamlari mavjud. O\'z razmeringizni tanlashga yordam berishimiz mumkin.'},
            {'type': 'qa', 'source': 'Asosiy', 'content': 'Savol: Yetkazib berish pullikmi?\nJavob: Viloyatlarga yetkazib berish (BTS orqali) 25,000 so\'m. 500,000 so\'mdan xarid qilsangiz, yetkazib berish BEPUL!'},
            {'type': 'qa', 'source': 'Asosiy', 'content': 'Savol: Qaytarish (vozvrat) bormi?\nJavob: Agar o\'lchami mos kelmasa yoki nuqsoni bo\'lsa, 3 kun ichida almashtirib yoki pullaringizni qaytarib beramiz (faqat kiyilmagan va yorliqlari olingan bo\'lsa).'},
            {'type': 'product', 'source': 'Erkaklar Kastyumi', 'content': 'Mahsulot: Erkaklar Classic Kastyumi\nNarx: 450000\nTavsif: Turkiya materiali, yozgi va kuzgi mavsum uchun mos. Ranglari: Qora, To\'q ko\'k, Kulrang.\nRasm: https://images.unsplash.com/photo-1594938298598-709772cd0cfa?q=80&w=600&auto=format&fit=crop'},
            {'type': 'product', 'source': 'Ayollar Ko\'ylagi', 'content': 'Mahsulot: Ayollar Yozgi Ko\'ylagi\nNarx: 280000\nTavsif: Paxta materiali, yengil va havo o\'tkazuvchan. Turli printlar mavjud.\nRasm: https://images.unsplash.com/photo-1572804013309-82a89b4f00e0?q=80&w=600&auto=format&fit=crop'}
        ]
    }
}
