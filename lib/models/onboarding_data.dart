class OnboardingData {
  String email;
  String fullName;
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
  String mainMarket;
  List<String> countries;
  List<String> cities;
  List<String> salesRegions;

  OnboardingData({
    this.email = '',
    this.fullName = '',
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
    this.mainMarket = '',
    List<String>? countries,
    List<String>? cities,
    List<String>? salesRegions,
  })  : products = products ?? [],
        countries = countries ?? [],
        cities = cities ?? [],
        salesRegions = salesRegions ?? [];
}
