class OnboardingData {
  String email;
  String fullName;
  String password;
  String companyQuery;
  String companyName;
  String companyInn;
  String companyCity;
  String companyIndustry;
  String role;
  String companySize;
  String businessType;
  String businessTypeSubtitle;
  List<String> products;
  /// Industry personalization (TZ electronics v1).
  List<String> brands;
  List<String> productCategories;
  List<String> productLines;
  List<String> procurementCountries;
  String activityRole;
  String mainMarket;
  List<String> countries;
  List<String> cities;
  List<String> salesRegions;
  List<String> finances;
  List<String> counterparties;

  OnboardingData({
    this.email = '',
    this.fullName = '',
    this.password = '',
    this.companyQuery = '',
    this.companyName = '',
    this.companyInn = '',
    this.companyCity = '',
    this.companyIndustry = '',
    this.role = '',
    this.companySize = '',
    this.businessType = '',
    this.businessTypeSubtitle = '',
    List<String>? products,
    List<String>? brands,
    List<String>? productCategories,
    List<String>? productLines,
    List<String>? procurementCountries,
    this.activityRole = '',
    this.mainMarket = '',
    List<String>? countries,
    List<String>? cities,
    List<String>? salesRegions,
    List<String>? finances,
    List<String>? counterparties,
  })  : products = products ?? [],
        brands = brands ?? [],
        productCategories = productCategories ?? [],
        productLines = productLines ?? [],
        procurementCountries = procurementCountries ?? [],
        countries = countries ?? [],
        cities = cities ?? [],
        salesRegions = salesRegions ?? [],
        finances = finances ?? [],
        counterparties = counterparties ?? [];

  Map<String, dynamic> toJson() => {
        'email': email,
        'fullName': fullName,
        'password': password,
        'companyQuery': companyQuery,
        'companyName': companyName,
        'companyInn': companyInn,
        'companyCity': companyCity,
        'companyIndustry': companyIndustry,
        'role': role,
        'companySize': companySize,
        'businessType': businessType,
        'businessTypeSubtitle': businessTypeSubtitle,
        'products': products,
        'brands': brands,
        'productCategories': productCategories,
        'productLines': productLines,
        'procurementCountries': procurementCountries,
        'activityRole': activityRole,
        'mainMarket': mainMarket,
        'countries': countries,
        'cities': cities,
        'salesRegions': salesRegions,
        'finances': finances,
        'counterparties': counterparties,
      };

  factory OnboardingData.fromJson(Map<String, dynamic> json) {
    List<String> listOf(dynamic value) {
      if (value is! List) return [];
      return [
        for (final item in value)
          if (item != null) item.toString(),
      ];
    }

    String str(dynamic value) => value?.toString() ?? '';

    return OnboardingData(
      email: str(json['email']),
      fullName: str(json['fullName']),
      password: str(json['password']),
      companyQuery: str(json['companyQuery']),
      companyName: str(json['companyName']),
      companyInn: str(json['companyInn']),
      companyCity: str(json['companyCity']),
      companyIndustry: str(json['companyIndustry']),
      role: str(json['role']),
      companySize: str(json['companySize']),
      businessType: str(json['businessType']),
      businessTypeSubtitle: str(json['businessTypeSubtitle']),
      products: listOf(json['products']),
      brands: listOf(json['brands']),
      productCategories: listOf(json['productCategories']),
      productLines: listOf(json['productLines']),
      procurementCountries: listOf(json['procurementCountries']),
      activityRole: str(json['activityRole']),
      mainMarket: str(json['mainMarket']),
      countries: listOf(json['countries']),
      cities: listOf(json['cities']),
      salesRegions: listOf(json['salesRegions']),
      finances: listOf(json['finances']),
      counterparties: listOf(json['counterparties']),
    );
  }
}
